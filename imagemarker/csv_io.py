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
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from .data_model import (
    STATUS_NO_ACTIVE,
    STATUS_OPEN,
    STATUS_PASS,
    STATUS_SHORT,
    ImageRecord,
    normalize_int,
)

BASE_HEADERS: Tuple[str, ...] = ("name", "row", "node", "label")

Key = Tuple[str, int, int]


def parse_label_value(value: Any) -> Optional[str]:
    """Normalise a label cell coming from an arbitrary CSV.

    Legacy numeric markers (``1`` -> Pass, ``-1`` -> Open) and the known label
    spellings are mapped onto the canonical status strings; anything else is
    preserved verbatim.  Blank / ``None`` / ``"None"`` become ``None``.
    """
    if value is None:
        return None

    text = str(value).strip()
    if not text:
        return None

    upper = text.upper()

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

    if upper in ("PASS", "P", "OK", "GOOD", "TRUE", "YES"):
        return STATUS_PASS
    if upper in ("NO ACTIVE", "NOACTIVE", "NO_ACT", "INACTIVE"):
        return STATUS_NO_ACTIVE
    if upper in ("OPEN", "OP"):
        return STATUS_OPEN
    if upper in ("SHORT", "SH"):
        return STATUS_SHORT
    if upper in ("NONE", "N/A", "NA", "AMBIGUOUS", "UNKNOWN", "UNCLASSIFIED"):
        return None

    return text


@dataclass
class CsvLabels:
    """Result of :func:`load_label_csv`."""

    headers: List[str] = field(default_factory=lambda: list(BASE_HEADERS))
    labels: Dict[Key, Optional[str]] = field(default_factory=dict)
    extras: Dict[Key, Dict[str, str]] = field(default_factory=dict)

    def __len__(self) -> int:
        return len(self.labels)


def load_label_csv(path: str) -> CsvLabels:
    """Load ``(name, row, node) -> label`` plus any extra columns."""
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
                record.get(label_col) if label_col else None
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
