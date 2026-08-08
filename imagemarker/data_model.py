"""Data model for ImageMarker.

Holds the image record dataclass and the record container (``ImageStore``) that
implements filtering, sorting, navigation and dirty tracking.

This module must stay free of any tkinter/Pillow import so that it can be unit
tested head-lessly (see ``tests/test_data_model.py``).
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Set, Tuple

# --------------------------------------------------------------------------- #
# Status values
# --------------------------------------------------------------------------- #

STATUS_PASS = "Pass"
STATUS_NO_ACTIVE = "No Active"
STATUS_NO_GATE_EFFECT = "No Gate Effect"
STATUS_OPEN = "Open"
STATUS_SHORT = "Short"

#: Label used in the UI (filter dropdown / info bar) for an empty status.
BLANK_DISPLAY = "(blank)"

#: Known status values, only used for ordering / colouring.  The real value set
#: is ALWAYS collected dynamically from the loaded data - unknown values are
#: never rejected.
KNOWN_STATUSES: Tuple[str, ...] = (
    STATUS_PASS,
    STATUS_NO_ACTIVE,
    STATUS_NO_GATE_EFFECT,
    STATUS_OPEN,
    STATUS_SHORT,
)

#: Row background colours by status (blank/unknown -> white).
STATUS_COLORS: Dict[Optional[str], str] = {
    STATUS_NO_ACTIVE: "lightblue",
    STATUS_OPEN: "lightcoral",
    STATUS_NO_GATE_EFFECT: "khaki",
    STATUS_PASS: "#d8f0d8",
    None: "white",
}

#: Foreground colour used for the big overlay flash.
STATUS_OVERLAY_COLORS: Dict[Optional[str], str] = {
    STATUS_NO_ACTIVE: "#4da6ff",
    STATUS_OPEN: "#ff6b6b",
    STATUS_NO_GATE_EFFECT: "khaki",
    STATUS_PASS: "#8ce68c",
    STATUS_SHORT: "orange",
    None: "white",
}

#: Metric columns carried over from the Excel/CSV source (never edited).
METRIC_COLUMNS: Tuple[str, ...] = (
    "ON",
    "OFF",
    "ON/OFF",
    "gm",
    "Vth",
    "Carrier Mobility",
)

#: ``<name>_rgb_<row>_<node>.png``
IMAGE_PATTERN = re.compile(r"^(.+)_rgb_(\d+)_(\d+)\.png$", re.IGNORECASE)


# --------------------------------------------------------------------------- #
# Value helpers
# --------------------------------------------------------------------------- #

def normalize_status(value: Any) -> Optional[str]:
    """Normalise a raw status cell to ``str`` or ``None`` (blank).

    The value set is open ended: any non-empty string is preserved verbatim
    (only surrounding whitespace is stripped).
    """
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def status_display(value: Optional[str]) -> str:
    """Human readable status for the filter menu / info bar."""
    return BLANK_DISPLAY if normalize_status(value) is None else str(value)


def normalize_int(value: Any) -> Optional[int]:
    """Normalise ``'01'`` / ``1`` / ``1.0`` to ``int``; ``None`` when unusable."""
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return int(value)
    if isinstance(value, float):
        return int(value) if float(value).is_integer() else None
    text = str(value).strip()
    if not text:
        return None
    try:
        return int(text)
    except ValueError:
        try:
            number = float(text)
        except ValueError:
            return None
        return int(number) if number.is_integer() else None


def to_float(value: Any) -> Optional[float]:
    """Best effort float conversion; ``None`` for blanks / non numeric text."""
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def format_metric(value: Optional[float]) -> str:
    """Format a metric for display.

    Scientific notation (``%.3e``) when ``0 < |v| < 1e-3`` or ``|v| >= 1e5``,
    otherwise up to 4 significant digits.  Blank for ``None``.
    """
    if value is None:
        return ""
    number = to_float(value)
    if number is None:
        return str(value)
    magnitude = abs(number)
    if magnitude != 0.0 and (magnitude < 1e-3 or magnitude >= 1e5):
        return "%.3e" % number
    return "%.4g" % number


def status_sort_key(value: Optional[str]) -> Tuple[int, str]:
    """Sort key placing blanks last, then alphabetical (case insensitive)."""
    normalized = normalize_status(value)
    if normalized is None:
        return (1, "")
    return (0, normalized.casefold())


# --------------------------------------------------------------------------- #
# Records
# --------------------------------------------------------------------------- #

@dataclass
class ImageRecord:
    """One RGB slice image plus the data row it was matched to."""

    name: str
    row: int
    node: int
    path: Optional[str] = None
    status: Optional[str] = None
    metrics: Dict[str, Optional[float]] = field(default_factory=dict)
    #: 1-based worksheet row index of the matched Excel row (``None`` if unmatched).
    excel_row: Optional[int] = None
    #: 1-based worksheet column index of the ``Status`` column.
    excel_status_col: Optional[int] = None
    #: ``True`` while the record has no backing data row.
    no_data: bool = True
    #: ``True`` when the status was edited but not yet saved.
    dirty: bool = False
    #: Extra CSV columns preserved verbatim on save.
    extra_fields: Dict[str, str] = field(default_factory=dict)

    @property
    def key(self) -> Tuple[int, int]:
        """``(row, node)`` join key."""
        return (self.row, self.node)

    @property
    def status_text(self) -> str:
        """Status as displayed in the table (blank instead of ``None``)."""
        return "" if self.status is None else str(self.status)

    def metric(self, column: str) -> Optional[float]:
        return self.metrics.get(column)

    def metric_text(self, column: str) -> str:
        return format_metric(self.metrics.get(column))

    def set_status(self, value: Any, mark_dirty: bool = True) -> bool:
        """Set the status, returning ``True`` when it actually changed."""
        new_value = normalize_status(value)
        if new_value == self.status:
            return False
        self.status = new_value
        if mark_dirty:
            self.dirty = True
        return True

    @property
    def can_write_back(self) -> bool:
        """``True`` when the record knows where to write its status back to."""
        return self.excel_row is not None and self.excel_status_col is not None


def parse_image_filename(filename: str) -> Optional[Tuple[str, int, int]]:
    """Parse ``<name>_rgb_<row>_<node>.png`` -> ``(name, row, node)``."""
    match = IMAGE_PATTERN.match(filename)
    if not match:
        return None
    name, row, node = match.groups()
    return name, int(row), int(node)


def parse_image_folder(folder: str) -> List[ImageRecord]:
    """Build records for every RGB slice image in ``folder``, sorted."""
    records: List[ImageRecord] = []
    for filename in sorted(os.listdir(folder)):
        parsed = parse_image_filename(filename)
        if parsed is None:
            continue
        name, row, node = parsed
        records.append(
            ImageRecord(
                name=name,
                row=row,
                node=node,
                path=os.path.join(folder, filename),
            )
        )
    records.sort(key=lambda record: (record.name, record.row, record.node))
    return records


# --------------------------------------------------------------------------- #
# Store
# --------------------------------------------------------------------------- #

class ImageStore:
    """Container for :class:`ImageRecord` objects.

    Owns the master (sorted) list, the status filter, the "current" record and
    the dirty bookkeeping.  Navigation and the position counter always operate
    on the FILTERED list.
    """

    def __init__(self, records: Optional[Sequence[ImageRecord]] = None) -> None:
        self._records: List[ImageRecord] = list(records or [])
        self._filter: Optional[Set[Optional[str]]] = None
        self._visible_cache: Optional[List[ImageRecord]] = None
        self._current: Optional[ImageRecord] = self._records[0] if self._records else None
        self._sort_column: Optional[str] = None
        self._sort_reverse: bool = False

    # -- container -------------------------------------------------------- #

    def __len__(self) -> int:
        return len(self._records)

    @property
    def records(self) -> List[ImageRecord]:
        """The full (unfiltered) record list."""
        return self._records

    def clear(self) -> None:
        self._records = []
        self._current = None
        self._filter = None
        self._invalidate()

    def set_records(self, records: Sequence[ImageRecord]) -> None:
        """Replace all records (resets filter, current and sort state)."""
        self._records = list(records)
        self._filter = None
        self._sort_column = None
        self._sort_reverse = False
        self._current = self._records[0] if self._records else None
        self._invalidate()

    def load_folder(self, folder: str) -> int:
        """Load every RGB image of ``folder``; returns the record count."""
        self.set_records(parse_image_folder(folder))
        return len(self._records)

    def _invalidate(self) -> None:
        self._visible_cache = None

    # -- statuses --------------------------------------------------------- #

    def unique_statuses(self) -> List[Optional[str]]:
        """Distinct status values present, blanks (``None``) last."""
        values: Set[Optional[str]] = {record.status for record in self._records}
        return sorted(values, key=status_sort_key)

    def status_counts(
        self, records: Optional[Iterable[ImageRecord]] = None
    ) -> Dict[Optional[str], int]:
        """Count records per status value."""
        source = self._records if records is None else records
        counts: Dict[Optional[str], int] = {}
        for record in source:
            counts[record.status] = counts.get(record.status, 0) + 1
        return counts

    # -- filtering -------------------------------------------------------- #

    @property
    def filter_values(self) -> Optional[Set[Optional[str]]]:
        """Currently allowed status values, or ``None`` when unfiltered."""
        return None if self._filter is None else set(self._filter)

    def set_filter(self, values: Optional[Iterable[Optional[str]]]) -> None:
        """Restrict the visible list to ``values`` (``None`` -> show all)."""
        if values is None:
            self._filter = None
        else:
            self._filter = {normalize_status(value) for value in values}
        self._invalidate()

    def matches_filter(self, record: ImageRecord) -> bool:
        return self._filter is None or record.status in self._filter

    @property
    def filter_active(self) -> bool:
        """``True`` when the filter actually hides something."""
        if self._filter is None:
            return False
        return not set(self.unique_statuses()).issubset(self._filter)

    def filter_description(self) -> str:
        """e.g. ``'No Active, (blank)'`` - empty string when not filtering."""
        if not self.filter_active:
            return ""
        selected = [value for value in self.unique_statuses() if value in self._filter]
        if not selected:
            return "(none)"
        return ", ".join(status_display(value) for value in selected)

    def visible(self) -> List[ImageRecord]:
        """The filtered record list, in current sort order."""
        if self._visible_cache is None:
            if self._filter is None:
                self._visible_cache = list(self._records)
            else:
                self._visible_cache = [
                    record for record in self._records if record.status in self._filter
                ]
        return self._visible_cache

    @property
    def visible_count(self) -> int:
        return len(self.visible())

    # -- current record / navigation -------------------------------------- #

    @property
    def current_record(self) -> Optional[ImageRecord]:
        return self._current

    @current_record.setter
    def current_record(self, record: Optional[ImageRecord]) -> None:
        self._current = record

    @property
    def current_index(self) -> int:
        """Index of the current record inside the FILTERED list (-1 if none)."""
        if self._current is None:
            return -1
        visible = self.visible()
        try:
            return visible.index(self._current)
        except ValueError:
            return -1

    def record_at(self, index: int) -> Optional[ImageRecord]:
        visible = self.visible()
        if 0 <= index < len(visible):
            return visible[index]
        return None

    def set_current_index(self, index: int) -> Optional[ImageRecord]:
        record = self.record_at(index)
        if record is not None:
            self._current = record
        return record

    def navigate(self, delta: int) -> Optional[ImageRecord]:
        """Move ``delta`` steps inside the filtered list (clamped)."""
        visible = self.visible()
        if not visible:
            return None
        index = self.current_index
        if index < 0:
            index = 0 if delta >= 0 else len(visible) - 1
        else:
            index += delta
        index = max(0, min(len(visible) - 1, index))
        self._current = visible[index]
        return self._current

    def ensure_current_visible(self) -> Optional[ImageRecord]:
        """Keep the current record valid after a filter change or status edit.

        When the current record no longer passes the filter the selection moves
        to the next visible row, or to the previous one when at the end.
        """
        visible = self.visible()
        if not visible:
            self._current = None
            return None
        if self._current is not None and self._current in visible:
            return self._current
        if self._current is None:
            self._current = visible[0]
            return self._current
        try:
            position = self._records.index(self._current)
        except ValueError:
            self._current = visible[0]
            return self._current
        for record in self._records[position + 1:]:
            if self.matches_filter(record):
                self._current = record
                return self._current
        for record in reversed(self._records[:position]):
            if self.matches_filter(record):
                self._current = record
                return self._current
        self._current = visible[0]
        return self._current

    # -- sorting ---------------------------------------------------------- #

    @property
    def sort_state(self) -> Tuple[Optional[str], bool]:
        return self._sort_column, self._sort_reverse

    def _sort_key_func(self, column: str):
        if column == "name":
            return lambda record: (record.name.casefold(), record.row, record.node)
        if column == "row":
            return lambda record: (record.row, record.node)
        if column == "node":
            return lambda record: (record.node, record.row)
        if column == "status":
            return lambda record: (status_sort_key(record.status), record.row, record.node)
        if column == "dirty":
            return lambda record: (not record.dirty, record.name, record.row, record.node)
        if column in METRIC_COLUMNS:
            def metric_key(record: ImageRecord):
                value = record.metrics.get(column)
                return (value is None, value if value is not None else 0.0)
            return metric_key
        raise KeyError(f"Unknown sort column: {column!r}")

    def sort_by(self, column: str, reverse: Optional[bool] = None) -> bool:
        """Sort the master list by ``column``; repeated calls toggle direction.

        The current record is tracked by identity, so after sorting the
        selection still points at the item the user was looking at (this is the
        prototype bug the spec asks to fix).
        """
        if reverse is None:
            reverse = not self._sort_reverse if self._sort_column == column else False
        self._records.sort(key=self._sort_key_func(column), reverse=reverse)
        self._sort_column = column
        self._sort_reverse = reverse
        self._invalidate()
        return reverse

    # -- editing / dirty state -------------------------------------------- #

    def apply_status(self, records: Iterable[ImageRecord], value: Any) -> List[ImageRecord]:
        """Apply ``value`` to every record; returns the records that changed."""
        changed: List[ImageRecord] = []
        for record in records:
            if record.set_status(value):
                changed.append(record)
        if changed:
            self._invalidate()
        return changed

    def dirty_records(self) -> List[ImageRecord]:
        return [record for record in self._records if record.dirty]

    @property
    def dirty_count(self) -> int:
        return sum(1 for record in self._records if record.dirty)

    def clear_dirty(self, records: Optional[Iterable[ImageRecord]] = None) -> None:
        for record in self._records if records is None else records:
            record.dirty = False

    # -- data source join -------------------------------------------------- #

    def apply_excel_rows(
        self, rows_by_key: Mapping[Tuple[int, int], Any]
    ) -> Tuple[int, int]:
        """Join Excel rows onto the records by ``(row, node)``.

        ``rows_by_key`` maps ``(row, node)`` to an object exposing ``status``,
        ``metrics``, ``sheet_row`` and ``status_col`` (see
        :class:`imagemarker.excel_io.ExcelRow`) - duck typed on purpose so the
        model stays independent of the IO layer.

        Returns ``(matched, unmatched)`` image counts.
        """
        matched = 0
        for record in self._records:
            source = rows_by_key.get(record.key)
            if source is None:
                record.metrics = {}
                record.status = None
                record.excel_row = None
                record.excel_status_col = None
                record.no_data = True
                record.dirty = False
                continue
            record.status = normalize_status(getattr(source, "status", None))
            record.metrics = dict(getattr(source, "metrics", {}) or {})
            record.excel_row = getattr(source, "sheet_row", None)
            record.excel_status_col = getattr(source, "status_col", None)
            record.no_data = False
            record.dirty = False
            matched += 1
        self._invalidate()
        return matched, len(self._records) - matched

    def apply_csv_labels(
        self,
        labels: Mapping[Tuple[str, int, int], Optional[str]],
        extras: Optional[Mapping[Tuple[str, int, int], Dict[str, str]]] = None,
    ) -> int:
        """Legacy CSV join by ``(name, row, node)``; returns matched count."""
        matched = 0
        for record in self._records:
            key = (record.name, record.row, record.node)
            if key not in labels:
                continue
            record.status = normalize_status(labels[key])
            record.no_data = False
            record.dirty = False
            if extras is not None:
                record.extra_fields = dict(extras.get(key, {}))
            matched += 1
        self._invalidate()
        return matched
