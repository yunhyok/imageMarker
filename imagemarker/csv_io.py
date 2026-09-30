"""Legacy CSV IO (``name,row,node,label`` + arbitrary extra columns).

Kept working exactly like the original prototype: the same header detection,
the same ``parse_label_value`` normalisation and extra columns preserved
verbatim on save.  Blank labels are represented as ``None`` (the data model's
blank status) instead of the prototype's ``"None"`` string.

No tkinter import here either.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Dict, Iterable, List, Optional, Sequence, Tuple

from .data_model import (
    STATUS_NO_ACTIVE,
    STATUS_OPEN,
    STATUS_PASS,
    STATUS_SHORT,
    ImageRecord,
    normalize_int,
)

if TYPE_CHECKING:  # pragma: no cover
    from .label_sets import LabelSet

BASE_HEADERS: Tuple[str, ...] = ("name", "row", "node", "label")

Key = Tuple[str, int, int]


#: Spellings the 1.x prototype accepted for its fixed statuses.  They are only
#: applied when the target status exists in the active label set, so a set
#: that defines ``GOOD`` keeps ``GOOD`` instead of turning it into ``Pass``.
LEGACY_ALIASES: Dict[str, str] = {
    "PASS": STATUS_PASS, "P": STATUS_PASS, "OK": STATUS_PASS, "GOOD": STATUS_PASS,
    "TRUE": STATUS_PASS, "YES": STATUS_PASS, "1": STATUS_PASS,
    "NO ACTIVE": STATUS_NO_ACTIVE, "NOACTIVE": STATUS_NO_ACTIVE,
    "NO_ACT": STATUS_NO_ACTIVE, "INACTIVE": STATUS_NO_ACTIVE,
    "OPEN": STATUS_OPEN, "OP": STATUS_OPEN, "-1": STATUS_OPEN,
    "SHORT": STATUS_SHORT, "SH": STATUS_SHORT,
}

#: Spellings that always mean "no label".
BLANK_ALIASES = frozenset({"NONE", "N/A", "NA", "AMBIGUOUS", "UNKNOWN", "UNCLASSIFIED"})


def parse_label_value(value: Any, label_set: Optional["LabelSet"] = None) -> Optional[str]:
    """Normalise a label cell coming from an arbitrary CSV.

    Blank / ``None`` / ``"None"`` become ``None``.  When ``label_set`` is given,
    a value that names one of its labels (case-insensitively) is returned in
    the set's own spelling, and the legacy aliases of the 1.x prototype
    (``1`` -> Pass, ``-1`` -> Open, ``good``/``ok`` -> Pass, ...) only apply
    when the aliased status is itself part of the set.  Without a label set the
    legacy behaviour is kept unchanged.  Anything else is preserved verbatim.
    """
    if value is None:
        return None

    text = str(value).strip()
    if not text:
        return None

    upper = text.upper()
    if upper in BLANK_ALIASES:
        return None

    if label_set is not None:
        label = label_set.find(text)
        if label is not None:
            return label.name
        aliased = LEGACY_ALIASES.get(upper)
        if aliased is not None and label_set.find(aliased) is not None:
            return label_set.canonical(aliased)
        return text

    try:
        number = int(upper)
    except ValueError:
        pass
    else:
        if number == 1:
            return STATUS_PASS
        if number == -1:
            return STATUS_OPEN
        return None

    return LEGACY_ALIASES.get(upper, text)


@dataclass
class CsvLabels:
    """Result of :func:`load_label_csv`."""

    headers: List[str] = field(default_factory=lambda: list(BASE_HEADERS))
    labels: Dict[Key, Optional[str]] = field(default_factory=dict)
    extras: Dict[Key, Dict[str, str]] = field(default_factory=dict)

    def __len__(self) -> int:
        return len(self.labels)


def load_label_csv(path: str, label_set: Optional["LabelSet"] = None) -> CsvLabels:
    """Load ``(name, row, node) -> label`` plus any extra columns.

    ``label_set`` (when given) canonicalises the label spelling, see
    :func:`parse_label_value`.
    """
    with open(path, "r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        headers = list(reader.fieldnames or [])
        header_map = {header.strip().lower(): header for header in headers if header}

        name_col = header_map.get("name")
        row_col = header_map.get("row")
        node_col = header_map.get("node")
        label_col = (
            header_map.get("label")
            or header_map.get("marker")
            or header_map.get("status")
        )

        base_cols = {name_col, row_col, node_col, label_col}
        extra_headers = [
            header for header in headers if header and header not in base_cols
        ]

        result = CsvLabels(headers=list(BASE_HEADERS) + extra_headers)

        for record in reader:
            name = (record.get(name_col, "") if name_col else "") or ""
            name = name.strip()
            row_value = normalize_int(record.get(row_col)) if row_col else None
            node_value = normalize_int(record.get(node_col)) if node_col else None
            key: Key = (name, row_value or 0, node_value or 0)

            result.labels[key] = parse_label_value(
                record.get(label_col) if label_col else None, label_set
            )
            result.extras[key] = {
                header: (record.get(header) or "") for header in extra_headers
            }

    return result


def save_label_csv(
    path: str,
    records: Iterable[ImageRecord],
    headers: Optional[Sequence[str]] = None,
) -> int:
    """Write ``records`` out as a legacy label CSV; returns the row count."""
    field_names = list(headers) if headers else list(BASE_HEADERS)
    for base in BASE_HEADERS:
        if base not in field_names:
            field_names.insert(BASE_HEADERS.index(base), base)
    extra_headers = [header for header in field_names if header not in BASE_HEADERS]

    count = 0
    with open(path, "w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=field_names)
        writer.writeheader()
        for record in records:
            row: Dict[str, Any] = {
                "name": record.name,
                "row": record.row,
                "node": record.node,
                "label": record.status_text,
            }
            for header in extra_headers:
                row[header] = record.extra_fields.get(header, "")
            writer.writerow(row)
            count += 1
    return count
