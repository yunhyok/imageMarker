"""Tests for imagemarker.excel_io.

All tests run against a small synthetic workbook created in ``tmp_path`` that
mimics the real file layout (10 meta columns + a few sweep columns, ``Row``
stored as text ``'01'`` in some cells and as ``int`` in others).  Nothing under
``V:\\`` is ever touched.
"""

from __future__ import annotations

import os
import stat
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import openpyxl
import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from imagemarker import excel_io  # noqa: E402
from imagemarker.data_model import ImageRecord, ImageStore  # noqa: E402
from imagemarker.excel_io import (  # noqa: E402
    ExcelFileLockedError,
    ExcelFormatError,
    ExcelSource,
    extract_sample_number,
    suggest_excel_name,
    suggest_name_mapping,
)

SHEET_NAME = "150px_20260619"
META_HEADER = [
    "Name",
    "Row",
    "Node",
    "ON",
    "OFF",
    "ON/OFF",
    "gm",
    "Vth",
    "Carrier Mobility",
    "Status",
]
SWEEP_HEADER = ["-20.00000", "-19.80000", "-19.60000", "-19.40000", "-19.20000"]

NAME_1 = "20260619-P3MEEMT(1-3)_7kgf_100_sam1"
NAME_2 = "20260619-P3MEEMT(1-3)_7kgf_100_sam2"

STATUS_COL = 10  # 1-based, matches the real file

#: (Name, Row-as-stored, Node, ON, OFF, ON/OFF, gm, Vth, Mobility, Status)
DATA_ROWS: List[Tuple] = [
    # sam1 stores Row as TEXT with a leading zero
    (NAME_1, "01", 1, 1.018096e-07, 2.701846e-08, 3.77, 13.88724, 31.8363, 0.0008, "Pass"),
    (NAME_1, "01", 2, 2.355151e-07, 1.804043e-07, 1.31, 6.634537, 81.4566, 0.0002,
     "No Gate Effect"),
    (NAME_1, "02", 1, 4.932187e-08, 4.528602e-08, 1.09, 2.215976, 80.2201, 0.0, None),
    (NAME_1, "02", 2, 5.100000e-08, 4.900000e-08, 1.04, 1.115976, 70.1201, 0.0, "   "),
    # sam2 stores Row as a real int, and carries an unexpected status value
    (NAME_2, 1, 1, 9.100000e-07, 8.100000e-08, 11.2, 22.5, 12.5, 0.0123, "  No Active  "),
    (NAME_2, 1, 2, 1.500000e-06, 1.100000e-07, 13.6, 25.5, 13.5, 0.0456, "Weird Status"),
    (NAME_2, 2, 1, 2.500000e-06, 2.100000e-07, 11.9, 27.5, 14.5, 0.0789, "Pass"),
]


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def build_workbook(path: Path, rows: Optional[List[Tuple]] = None) -> Path:
    """Create a synthetic data workbook that mimics the real layout."""
    rows = DATA_ROWS if rows is None else rows
    workbook = openpyxl.Workbook()
    worksheet = workbook.active
    worksheet.title = SHEET_NAME
    worksheet.append(META_HEADER + SWEEP_HEADER)
    for index, row in enumerate(rows):
        sweep = [round(1e-7 + index * 1e-8 + column * 1e-9, 12) for column in range(len(SWEEP_HEADER))]
        worksheet.append(list(row) + sweep)
    workbook.save(path)
    workbook.close()
    return path


@pytest.fixture()
def workbook_path(tmp_path: Path) -> Path:
    return build_workbook(tmp_path / "20260619_low_yield_150px_data.xlsx")


def read_grid(path: Path) -> Dict[Tuple[int, int], object]:
    """Snapshot every cell value of the workbook (row, column) -> value."""
    workbook = openpyxl.load_workbook(path)
    worksheet = workbook[workbook.sheetnames[0]]
    grid: Dict[Tuple[int, int], object] = {}
    for row in worksheet.iter_rows():
        for cell in row:
            grid[(cell.row, cell.column)] = cell.value
    workbook.close()
    return grid


def make_records(name: str, keys: List[Tuple[int, int]]) -> List[ImageRecord]:
    return [
        ImageRecord(name=name, row=row, node=node, path="%s_rgb_%02d_%02d.png" % (name, row, node))
        for row, node in keys
    ]


# --------------------------------------------------------------------------- #
# Loading
# --------------------------------------------------------------------------- #

def test_load_parses_and_normalizes(workbook_path: Path) -> None:
    source = ExcelSource.load(str(workbook_path))

    assert source.sheet_name == SHEET_NAME
    assert source.status_col == STATUS_COL
    assert len(source.rows) == len(DATA_ROWS)

    first = source.rows[0]
    assert first.name == NAME_1
    assert first.row == 1 and isinstance(first.row, int)  # '01' -> 1
    assert first.node == 1
    assert first.status == "Pass"
    assert first.sheet_row == 2  # header is row 1
    assert first.status_col == STATUS_COL
    assert first.metrics["ON"] == pytest.approx(1.018096e-07)
    assert first.metrics["Carrier Mobility"] == pytest.approx(0.0008)

    # int-stored Row values normalise identically
    sam2_first = source.rows[4]
    assert sam2_first.row == 1 and isinstance(sam2_first.row, int)
    assert sam2_first.sheet_row == 6

    # blank / whitespace-only statuses become None
    assert source.rows[2].status is None
    assert source.rows[3].status is None
    # surrounding whitespace is stripped, the value itself is preserved
    assert sam2_first.status == "No Active"
    # unknown values are never rejected
    assert source.rows[5].status == "Weird Status"

    # every parsed row remembers its worksheet position
    for row in source.rows:
        assert row.status_col == STATUS_COL
        assert 2 <= row.sheet_row <= len(DATA_ROWS) + 1


def test_sheet_row_index_survives_blank_rows(tmp_path: Path) -> None:
    rows = [
        DATA_ROWS[0],
        tuple([None] * len(META_HEADER)),  # completely empty row
        DATA_ROWS[1],
    ]
    path = build_workbook(tmp_path / "gap.xlsx", rows)
    source = ExcelSource.load(str(path))

    assert [row.sheet_row for row in source.rows] == [2, 4]

    workbook = openpyxl.load_workbook(path)
    worksheet = workbook[SHEET_NAME]
    for row in source.rows:
        assert worksheet.cell(row=row.sheet_row, column=3).value == row.node
    workbook.close()


def test_names_with_counts(workbook_path: Path) -> None:
    source = ExcelSource.load(str(workbook_path))
    assert source.names() == [(NAME_1, 4), (NAME_2, 3)]


def test_unique_statuses_collected_dynamically(workbook_path: Path) -> None:
    source = ExcelSource.load(str(workbook_path))
    assert set(source.unique_statuses()) == {
        "Pass",
        "No Gate Effect",
        None,
        "No Active",
        "Weird Status",
    }
    assert set(source.unique_statuses(NAME_2)) == {"No Active", "Weird Status", "Pass"}


def test_missing_status_column_raises(tmp_path: Path) -> None:
    workbook = openpyxl.Workbook()
    worksheet = workbook.active
    worksheet.append(["Name", "Row", "Node", "ON"])
    worksheet.append(["x", "01", 1, 0.5])
    path = tmp_path / "bad.xlsx"
    workbook.save(path)
    workbook.close()

    with pytest.raises(ExcelFormatError) as info:
        ExcelSource.load(str(path))
    assert "Status" in str(info.value)


# --------------------------------------------------------------------------- #
# Name suggestion + (row, node) matching
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize(
    "text, expected",
    [
        ("260619 p3meet ac 7kg 100mm, SAM 1", 1),
        ("260619 p3meemt ac 7kgf 100mm, SAM 2", 2),
        ("20260619-P3MEEMT(1-3)_7kgf_100_sam1", 1),
        ("260701 p3meemt 8mg-ac 8kgf 350- sam 11_2", 11),
        ("no sample number here", None),
        (None, None),
    ],
)
def test_extract_sample_number(text: Optional[str], expected: Optional[int]) -> None:
    assert extract_sample_number(text) == expected


def test_suggest_excel_name(workbook_path: Path) -> None:
    source = ExcelSource.load(str(workbook_path))

    # the image prefix never equals the Excel Name - matching is by sample number
    assert source.suggest_name("260619 p3meet ac 7kg 100mm, SAM 1") == NAME_1
    assert source.suggest_name("260619 p3meemt ac 7kgf 100mm, SAM 2") == NAME_2
    # no sample number -> no suggestion
    assert source.suggest_name("unrelated folder") is None
    # ambiguous (two Excel names share the number) -> no suggestion
    assert suggest_excel_name("sam 1", ["a_sam1", "b_sam1"]) is None


def test_suggest_mapping_pairs_every_prefix_with_its_own_name(
    workbook_path: Path,
) -> None:
    """A recursive load brings several samples in at once - each gets a suggestion."""
    source = ExcelSource.load(str(workbook_path))
    prefixes = [
        "260619 p3meet ac 7kg 100mm, SAM 1",
        "260619 p3meemt ac 7kgf 100mm, SAM 2",
        "260701 p3meemt 8mg-ac 8kgf 350- sam 11_2",  # no Excel counterpart
        "unrelated folder",  # no sample number at all
    ]

    mapping = source.suggest_mapping(prefixes)

    assert mapping == {
        "260619 p3meet ac 7kg 100mm, SAM 1": NAME_1,
        "260619 p3meemt ac 7kgf 100mm, SAM 2": NAME_2,
        "260701 p3meemt 8mg-ac 8kgf 350- sam 11_2": None,
        "unrelated folder": None,
    }
    # the prefix order is preserved so the dialog rows stay stable
    assert list(mapping) == prefixes


def test_suggest_name_mapping_handles_duplicates_and_ambiguity() -> None:
    # repeated prefixes collapse to a single entry
    assert suggest_name_mapping(["sam 1", "sam 1"], ["x_sam1"]) == {"sam 1": "x_sam1"}
    # ambiguous numbers yield no suggestion, the rest are unaffected
    assert suggest_name_mapping(
        ["sam 1", "sam 2"], ["a_sam1", "b_sam1", "only_sam2"]
    ) == {"sam 1": None, "sam 2": "only_sam2"}
    assert suggest_name_mapping([], ["a_sam1"]) == {}


def test_multi_prefix_join_matches_each_sample_to_its_own_name(
    workbook_path: Path,
) -> None:
    source = ExcelSource.load(str(workbook_path))
    prefix_1 = "260619 p3meet ac 7kg 100mm, SAM 1"
    prefix_2 = "260619 p3meemt ac 7kgf 100mm, SAM 2"
    prefix_3 = "260701 p3meemt 8mg-ac 8kgf 350- sam 11_2"

    records = (
        make_records(prefix_1, [(1, 1), (2, 2)])
        + make_records(prefix_2, [(1, 1), (1, 2), (9, 9)])
        + make_records(prefix_3, [(1, 1)])  # skipped by the user
    )
    store = ImageStore(records)

    mapping = source.suggest_mapping([prefix_1, prefix_2, prefix_3])
    indexes = {
        prefix: source.index_for_name(name)
        for prefix, name in mapping.items()
        if name is not None
    }
    stats = store.apply_excel_rows(indexes)

    assert stats == {prefix_1: (2, 0), prefix_2: (2, 1), prefix_3: (0, 1)}

    # sam1 rows came from NAME_1 ...
    assert store.records[0].status == "Pass"
    assert store.records[0].excel_row == 2
    # ... and sam2 rows from NAME_2, in the same store
    assert store.records[2].status == "No Active"
    assert store.records[2].excel_row == 6
    assert store.records[3].status == "Weird Status"
    # unmatched / skipped records keep no data at all
    assert store.records[4].no_data is True
    assert store.records[5].no_data is True and store.records[5].excel_row is None


def test_records_of_different_names_can_be_dirty_together(workbook_path: Path) -> None:
    """Write-back is per record, so a multi-sample session saves in one go."""
    before = read_grid(workbook_path)
    source = ExcelSource.load(str(workbook_path))
    store = ImageStore(make_records("a", [(1, 1)]) + make_records("b", [(1, 1)]))
    store.apply_excel_rows(
        {"a": source.index_for_name(NAME_1), "b": source.index_for_name(NAME_2)}
    )

    store.apply_status([store.records[0]], "Short")  # NAME_1, sheet row 2
    store.apply_status([store.records[1]], "Open")  # NAME_2, sheet row 6
    assert store.dirty_count == 2

    written, backup_created, skipped = source.write_records(store.dirty_records())
    assert (written, backup_created, skipped) == (2, True, 0)

    after = read_grid(workbook_path)
    changed = {key for key in before if before[key] != after[key]}
    assert changed == {(2, STATUS_COL), (6, STATUS_COL)}
    assert after[(2, STATUS_COL)] == "Short"
    assert after[(6, STATUS_COL)] == "Open"


def test_row_node_matching_joins_images_to_excel(workbook_path: Path) -> None:
    source = ExcelSource.load(str(workbook_path))
    index = source.index_for_name(NAME_1)
    assert set(index) == {(1, 1), (1, 2), (2, 1), (2, 2)}

    store = ImageStore(make_records("folder_prefix", [(1, 1), (1, 2), (2, 1), (9, 9)]))
    stats = store.apply_excel_rows({"folder_prefix": index})

    assert stats == {"folder_prefix": (3, 1)}
    first = store.records[0]
    assert first.status == "Pass"
    assert first.excel_row == 2
    assert first.excel_status_col == STATUS_COL
    assert first.no_data is False
    assert first.metrics["ON/OFF"] == pytest.approx(3.77)

    orphan = store.records[3]
    assert orphan.no_data is True
    assert orphan.status is None
    assert orphan.metrics == {}
    assert orphan.excel_row is None

    # the other Name is not visible through this index
    assert (1, 1) in source.index_for_name(NAME_2)
    assert source.index_for_name(NAME_2)[(1, 1)].status == "No Active"


# --------------------------------------------------------------------------- #
# Write back
# --------------------------------------------------------------------------- #

def test_write_back_touches_only_dirty_status_cells(workbook_path: Path) -> None:
    before = read_grid(workbook_path)

    source = ExcelSource.load(str(workbook_path))
    store = ImageStore(make_records("prefix", [(1, 1), (1, 2), (2, 1), (2, 2)]))
    store.apply_excel_rows({"prefix": source.index_for_name(NAME_1)})

    # edit two records only
    target_a = store.records[0]  # sheet row 2, 'Pass'   -> 'No Active'
    target_b = store.records[2]  # sheet row 4, blank    -> 'Open'
    store.apply_status([target_a], "No Active")
    store.apply_status([target_b], "Open")
    assert store.dirty_count == 2

    written, backup_created, skipped = source.write_records(store.dirty_records())
    assert (written, backup_created, skipped) == (2, True, 0)

    after = read_grid(workbook_path)
    assert set(after) == set(before)

    changed = {key for key in before if before[key] != after[key]}
    assert changed == {(2, STATUS_COL), (4, STATUS_COL)}
    assert after[(2, STATUS_COL)] == "No Active"
    assert after[(4, STATUS_COL)] == "Open"

    # every other cell - notably the sweep columns - is byte-identical
    for key, value in before.items():
        if key in changed:
            continue
        assert after[key] == value
        assert type(after[key]) is type(value)

    sweep_columns = range(len(META_HEADER) + 1, len(META_HEADER) + len(SWEEP_HEADER) + 1)
    for sheet_row in range(1, len(DATA_ROWS) + 2):
        for column in sweep_columns:
            assert after[(sheet_row, column)] == before[(sheet_row, column)]

    # in-memory rows stay consistent with the file
    reloaded = ExcelSource.load(str(workbook_path))
    assert reloaded.index_for_name(NAME_1)[(1, 1)].status == "No Active"
    assert reloaded.index_for_name(NAME_1)[(2, 1)].status == "Open"


def test_clearing_a_status_writes_a_blank_cell(workbook_path: Path) -> None:
    source = ExcelSource.load(str(workbook_path))
    source.write_statuses([(2, STATUS_COL, None)])
    assert read_grid(workbook_path)[(2, STATUS_COL)] is None


def test_backup_is_created_once(workbook_path: Path) -> None:
    source = ExcelSource.load(str(workbook_path))
    backup = Path(source.backup_path)

    assert backup.name == "20260619_low_yield_150px_data.backup.xlsx"
    assert backup.parent == workbook_path.parent
    assert not backup.exists()

    written, backup_created = source.write_statuses([(2, STATUS_COL, "Open")])
    assert (written, backup_created) == (1, True)
    assert backup.exists()

    # the first backup must never be overwritten by later saves
    backup.write_bytes(b"sentinel-original-copy")
    written, backup_created = source.write_statuses([(3, STATUS_COL, "Short")])
    assert (written, backup_created) == (1, False)
    assert backup.read_bytes() == b"sentinel-original-copy"


def test_write_statuses_without_updates_is_a_noop(workbook_path: Path) -> None:
    source = ExcelSource.load(str(workbook_path))
    assert source.write_statuses([]) == (0, False)
    assert not Path(source.backup_path).exists()


def test_records_without_an_excel_row_are_skipped(workbook_path: Path) -> None:
    source = ExcelSource.load(str(workbook_path))
    store = ImageStore(make_records("prefix", [(1, 1), (9, 9)]))
    store.apply_excel_rows({"prefix": source.index_for_name(NAME_1)})
    store.apply_status(store.records, "Short")

    written, _, skipped = source.write_records(store.dirty_records())
    assert (written, skipped) == (1, 1)


def test_excel_join_captures_the_original_status(workbook_path: Path) -> None:
    source = ExcelSource.load(str(workbook_path))
    store = ImageStore(make_records("prefix", [(1, 1), (2, 1), (9, 9)]))
    store.apply_excel_rows({"prefix": source.index_for_name(NAME_1)})

    labelled, blank, orphan = store.records
    assert (labelled.status, labelled.original_status) == ("Pass", "Pass")
    assert (blank.status, blank.original_status) == (None, None)
    assert (orphan.status, orphan.original_status) == (None, None)
    assert store.dirty_count == 0


def test_reverted_records_are_not_written_back(workbook_path: Path) -> None:
    """Right-then-Left leaves the workbook completely untouched."""
    before = read_grid(workbook_path)
    source = ExcelSource.load(str(workbook_path))
    store = ImageStore(make_records("prefix", [(1, 1), (1, 2)]))
    store.apply_excel_rows({"prefix": source.index_for_name(NAME_1)})

    reverted, kept = store.records
    store.apply_status([reverted], "Open")  # 'Pass' -> 'Open'
    store.apply_status([kept], "Short")
    assert store.dirty_count == 2

    store.revert_status([reverted])
    assert reverted.status == "Pass"
    assert store.dirty_records() == [kept]

    written, _, skipped = source.write_records(store.dirty_records())
    assert (written, skipped) == (1, 0)

    after = read_grid(workbook_path)
    changed = {key for key in before if before[key] != after[key]}
    assert changed == {(3, STATUS_COL)}  # only the row that stayed edited
    assert after[(2, STATUS_COL)] == "Pass"  # the reverted row is as it was


def test_save_moves_the_revert_target_to_the_saved_value(workbook_path: Path) -> None:
    source = ExcelSource.load(str(workbook_path))
    store = ImageStore(make_records("prefix", [(1, 1)]))
    store.apply_excel_rows({"prefix": source.index_for_name(NAME_1)})
    record = store.records[0]
    assert record.original_status == "Pass"

    store.apply_status([record], "Open")
    dirty = store.dirty_records()
    written, _, _ = source.write_records(dirty)
    assert written == 1
    store.clear_dirty([r for r in dirty if r.can_write_back])  # as save_excel does
    assert store.dirty_count == 0
    assert record.original_status == "Open"

    # a revert after the save restores the SAVED value, not the pre-session one
    store.apply_status([record], "Short")
    assert store.dirty_count == 1
    store.revert_status([record])
    assert record.status == "Open"
    assert store.dirty_count == 0
    assert read_grid(workbook_path)[(2, STATUS_COL)] == "Open"


def test_permission_error_is_reported_as_a_clean_exception(
    workbook_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = ExcelSource.load(str(workbook_path))

    def locked(*args, **kwargs):
        raise PermissionError(13, "The process cannot access the file")

    monkeypatch.setattr(excel_io.openpyxl, "load_workbook", locked)

    with pytest.raises(ExcelFileLockedError) as info:
        source.write_statuses([(2, STATUS_COL, "Open")])

    message = str(info.value)
    assert "Close the file in Excel" in message
    assert workbook_path.name in message
    assert info.value.path == str(workbook_path)


def test_read_only_file_raises_excel_file_locked_error(workbook_path: Path) -> None:
    source = ExcelSource.load(str(workbook_path))
    backup = Path(source.backup_path)
    os.chmod(workbook_path, stat.S_IREAD)
    try:
        with pytest.raises(ExcelFileLockedError):
            source.write_statuses([(2, STATUS_COL, "Open")])
    finally:
        os.chmod(workbook_path, stat.S_IWRITE | stat.S_IREAD)
        if backup.exists():
            os.chmod(backup, stat.S_IWRITE | stat.S_IREAD)

    # the source file is left untouched by the failed save
    assert read_grid(workbook_path)[(2, STATUS_COL)] == "Pass"


def test_loading_a_locked_file_raises_excel_file_locked_error(
    workbook_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def locked(*args, **kwargs):
        raise PermissionError(13, "The process cannot access the file")

    monkeypatch.setattr(excel_io.openpyxl, "load_workbook", locked)
    with pytest.raises(ExcelFileLockedError):
        ExcelSource.load(str(workbook_path))
