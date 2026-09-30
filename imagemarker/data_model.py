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

# Statuses of the fixed set ImageMarker 1.x shipped with.  Since v2.0 the
# label set is configurable (see :mod:`imagemarker.label_sets`); these
# constants only remain for the legacy CSV aliases, the "Electrical (legacy
# 1.x)" preset and backwards compatible imports.
STATUS_PASS = "Pass"
STATUS_NO_ACTIVE = "No Active"
STATUS_NO_GATE_EFFECT = "No Gate Effect"
STATUS_OPEN = "Open"
STATUS_SHORT = "Short"

#: Label used in the UI (filter dropdown / info bar) for an empty status.
BLANK_DISPLAY = "(blank)"

#: Statuses of the legacy 1.x set, only used for ordering / colouring by code
#: that has no label set at hand.  The real value set is ALWAYS collected
#: dynamically from the loaded data - unknown values are never rejected.
KNOWN_STATUSES: Tuple[str, ...] = (
    STATUS_PASS,
    STATUS_NO_ACTIVE,
    STATUS_NO_GATE_EFFECT,
    STATUS_OPEN,
    STATUS_SHORT,
)

#: Legacy row background colours (the active label set decides in the UI).
STATUS_COLORS: Dict[Optional[str], str] = {
    STATUS_NO_ACTIVE: "lightblue",
    STATUS_OPEN: "lightcoral",
    STATUS_NO_GATE_EFFECT: "khaki",
    STATUS_PASS: "#d8f0d8",
    None: "white",
}

#: Legacy overlay flash colours (the active label set decides in the UI).
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
    #: The status the record officially has in the source file: blank after a
    #: bare folder load, the joined value after an Excel/CSV load and the saved
    #: value after a successful save.  It is what ``Left`` reverts to and what
    #: :attr:`dirty` is measured against.
    original_status: Optional[str] = None
    metrics: Dict[str, Optional[float]] = field(default_factory=dict)
    #: 1-based worksheet row index of the matched Excel row (``None`` if unmatched).
    excel_row: Optional[int] = None
    #: 1-based worksheet column index of the ``Status`` column.
    excel_status_col: Optional[int] = None
    #: ``True`` while the record has no backing data row.
    no_data: bool = True
    #: Extra CSV columns preserved verbatim on save.
    extra_fields: Dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.status = normalize_status(self.status)
        # A record built with a status but no explicit original describes a
        # freshly loaded row, so it starts out clean.
        self.original_status = (
            self.status
            if self.original_status is None
            else normalize_status(self.original_status)
        )

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

    @property
    def dirty(self) -> bool:
        """``True`` while the status differs from the one in the source file.

        Dirtiness is derived from the values rather than latched by a flag, so
        undoing an edit - by reverting or by simply retyping the original
        label - brings the record back to a clean state on its own.
        """
        return normalize_status(self.status) != normalize_status(self.original_status)

    def set_status(self, value: Any) -> bool:
        """Set the status, returning ``True`` when it actually changed."""
        new_value = normalize_status(value)
        if new_value == self.status:
            return False
        self.status = new_value
        return True

    def load_status(self, value: Any) -> None:
        """Adopt ``value`` as both the current and the officially stored status."""
        self.status = normalize_status(value)
        self.original_status = self.status

    def commit_status(self) -> None:
        """Remember the current status as the one the source file now holds."""
        self.original_status = self.status

    def revert_status(self) -> bool:
        """Restore the source file's status; ``True`` when it actually changed."""
        return self.set_status(self.original_status)

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


@dataclass
class FolderScanResult:
    """Outcome of a recursive image-folder scan."""

    root: str
    records: List[ImageRecord] = field(default_factory=list)
    #: Paths that were skipped because their ``(name, row, node)`` was already
    #: seen in an earlier (walk-order) folder.
    duplicate_paths: List[str] = field(default_factory=list)
    #: Folders that contained at least one image, relative to ``root``
    #: (``'.'`` for the selected folder itself), in walk order.
    folders: List[str] = field(default_factory=list)

    def __len__(self) -> int:
        return len(self.records)

    @property
    def count(self) -> int:
        return len(self.records)

    @property
    def duplicate_count(self) -> int:
        return len(self.duplicate_paths)

    @property
    def folder_count(self) -> int:
        return len(self.folders)


def scan_image_folder(folder: str) -> FolderScanResult:
    """Recursively collect every RGB slice image below ``folder``.

    ``os.walk`` is driven with sorted directory and file names so the traversal
    order is deterministic.  When the same ``(name, row, node)`` shows up in
    more than one subfolder the FIRST one encountered wins and the rest are
    recorded in :attr:`FolderScanResult.duplicate_paths`.

    The returned records are sorted by ``(name, row, node)`` and each keeps the
    actual path of the file it was found at.
    """
    result = FolderScanResult(root=folder)
    seen: Set[Tuple[str, int, int]] = set()

    for dirpath, dirnames, filenames in os.walk(folder):
        dirnames.sort()
        found_here = False
        for filename in sorted(filenames):
            parsed = parse_image_filename(filename)
            if parsed is None:
                continue
            found_here = True
            name, row, node = parsed
            path = os.path.join(dirpath, filename)
            if (name, row, node) in seen:
                result.duplicate_paths.append(path)
                continue
            seen.add((name, row, node))
            result.records.append(
                ImageRecord(name=name, row=row, node=node, path=path)
            )
        if found_here:
            result.folders.append(os.path.relpath(dirpath, folder))

    result.records.sort(key=lambda record: (record.name, record.row, record.node))
    return result


def parse_image_folder(folder: str) -> List[ImageRecord]:
    """Records for every RGB slice image in ``folder`` and its subfolders."""
    return scan_image_folder(folder).records


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

    def load_folder(self, folder: str) -> FolderScanResult:
        """Load every RGB image of ``folder`` *and its subfolders*.

        Returns the full :class:`FolderScanResult` so the caller can report the
        number of image folders that were walked and how many duplicate
        ``(name, row, node)`` files were skipped.
        """
        result = scan_image_folder(folder)
        self.set_records(result.records)
        return result

    def name_counts(self) -> List[Tuple[str, int]]:
        """Distinct image name prefixes with their image counts, sorted."""
        counts: Dict[str, int] = {}
        for record in self._records:
            counts[record.name] = counts.get(record.name, 0) + 1
        return sorted(counts.items())

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

    def revert_status(self, records: Iterable[ImageRecord]) -> List[ImageRecord]:
        """Restore every record's original status; returns the ones that changed."""
        changed: List[ImageRecord] = []
        for record in records:
            if record.revert_status():
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
        """Mark the current statuses as saved (call after a successful write).

        ``dirty`` is value based, so "clearing" it means recording that the
        source file now holds the current status - which is also what a later
        revert will restore.
        """
        for record in self._records if records is None else records:
            record.commit_status()

    # -- data source join -------------------------------------------------- #

    def apply_excel_rows(
        self, indexes_by_prefix: Mapping[str, Mapping[Tuple[int, int], Any]]
    ) -> Dict[str, Tuple[int, int]]:
        """Join Excel rows onto the records, one index per image name prefix.

        A recursive folder load can contain several samples, each with its own
        ``Name`` in the workbook, so the join is driven by a mapping of image
        name prefix -> ``(row, node)`` index (as produced by
        :meth:`imagemarker.excel_io.ExcelSource.index_for_name`).  Prefixes the
        user chose to skip are simply absent from ``indexes_by_prefix``; their
        records are cleared like any other unmatched record.

        Each index maps ``(row, node)`` to an object exposing ``status``,
        ``metrics``, ``sheet_row`` and ``status_col`` (see
        :class:`imagemarker.excel_io.ExcelRow`) - duck typed on purpose so the
        model stays independent of the IO layer.

        Returns ``{image prefix: (matched, unmatched)}`` covering every prefix
        present in the store.
        """
        stats: Dict[str, List[int]] = {}
        for record in self._records:
            counters = stats.setdefault(record.name, [0, 0])
            index = indexes_by_prefix.get(record.name)
            source = None if index is None else index.get(record.key)
            if source is None:
                record.metrics = {}
                record.load_status(None)
                record.excel_row = None
                record.excel_status_col = None
                record.no_data = True
                counters[1] += 1
                continue
            # The joined value is what the workbook officially holds, so it
            # becomes both the current and the original status (clean record).
            record.load_status(getattr(source, "status", None))
            record.metrics = dict(getattr(source, "metrics", {}) or {})
            record.excel_row = getattr(source, "sheet_row", None)
            record.excel_status_col = getattr(source, "status_col", None)
            record.no_data = False
            counters[0] += 1
        self._invalidate()
        return {
            prefix: (counters[0], counters[1]) for prefix, counters in stats.items()
        }

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
            record.load_status(labels[key])
            record.no_data = False
            if extras is not None:
                record.extra_fields = dict(extras.get(key, {}))
            matched += 1
        self._invalidate()
        return matched
