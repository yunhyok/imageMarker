"""Tests for imagemarker.data_model (no GUI, no Excel needed)."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import List, Optional

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from imagemarker.data_model import (  # noqa: E402
    BLANK_DISPLAY,
    STATUS_NO_ACTIVE,
    STATUS_OPEN,
    STATUS_PASS,
    ImageRecord,
    ImageStore,
    format_metric,
    normalize_int,
    normalize_status,
    parse_image_filename,
    parse_image_folder,
    scan_image_folder,
    status_display,
)


def make_store(statuses: List[Optional[str]]) -> ImageStore:
    """Store with one record per status, nodes 1..n of row 1."""
    records = [
        ImageRecord(name="sample", row=1, node=index + 1, status=status)
        for index, status in enumerate(statuses)
    ]
    return ImageStore(records)


# --------------------------------------------------------------------------- #
# Value helpers
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize(
    "filename, expected",
    [
        ("sample_rgb_01_07.png", ("sample", 1, 7)),
        ("a_b_c_rgb_26_38.PNG", ("a_b_c", 26, 38)),
        ("sample_rgb_1_2.png", ("sample", 1, 2)),
        ("sample_rgb_01.png", None),
        ("sample_01_07.png", None),
        ("notes.txt", None),
    ],
)
def test_parse_image_filename(filename, expected):
    assert parse_image_filename(filename) == expected


def test_parse_image_folder_sorted_and_filtered(tmp_path: Path) -> None:
    for filename in (
        "s1_rgb_02_01.png",
        "s1_rgb_01_10.png",
        "s1_rgb_01_02.png",
        "s0_rgb_05_05.png",
        "thumbs.db",
        "s1_rgb_bad.png",
    ):
        (tmp_path / filename).write_bytes(b"")

    records = parse_image_folder(str(tmp_path))

    assert [(r.name, r.row, r.node) for r in records] == [
        ("s0", 5, 5),
        ("s1", 1, 2),
        ("s1", 1, 10),
        ("s1", 2, 1),
    ]
    assert all(Path(record.path).exists() for record in records)
    assert all(record.no_data and not record.dirty for record in records)


# --------------------------------------------------------------------------- #
# Recursive folder scanning
# --------------------------------------------------------------------------- #

def test_parse_image_folder_includes_subfolders(tmp_path: Path) -> None:
    (tmp_path / "nested").mkdir()
    (tmp_path / "nested" / "s1_rgb_01_01.png").write_bytes(b"")
    (tmp_path / "s0_rgb_01_01.png").write_bytes(b"")

    records = parse_image_folder(str(tmp_path))

    assert [(r.name, r.row, r.node) for r in records] == [("s0", 1, 1), ("s1", 1, 1)]


def make_images(folder: Path, filenames: List[str]) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    for filename in filenames:
        (folder / filename).write_bytes(b"")


def test_scan_walks_subfolders(tmp_path: Path) -> None:
    """A folder of ``<sample>_slices`` subfolders loads as one set."""
    make_images(tmp_path / "s1_slices", ["s1_rgb_01_02.png", "s1_rgb_01_01.png"])
    make_images(tmp_path / "s2_slices", ["s2_rgb_02_01.png", "s2_rgb_01_01.png"])
    make_images(tmp_path / "s2_slices" / "deeper", ["s3_rgb_05_05.png"])
    make_images(tmp_path, ["top_rgb_09_09.png", "notes.txt", "s1_slice_manifest.json"])

    scan = scan_image_folder(str(tmp_path))

    # every subfolder level is included, sorted by (name, row, node)
    assert [(r.name, r.row, r.node) for r in scan.records] == [
        ("s1", 1, 1),
        ("s1", 1, 2),
        ("s2", 1, 1),
        ("s2", 2, 1),
        ("s3", 5, 5),
        ("top", 9, 9),
    ]
    assert scan.count == 6
    assert scan.duplicate_count == 0
    # the selected folder itself plus the three subfolders holding images
    assert scan.folder_count == 4
    assert sorted(scan.folders) == sorted(
        [".", "s1_slices", "s2_slices", os.path.join("s2_slices", "deeper")]
    )

    # each record keeps the real path of the file it was found at
    for record in scan.records:
        assert Path(record.path).exists()
    by_name = {record.name: record for record in scan.records}
    assert Path(by_name["s1"].path).parent.name == "s1_slices"
    assert Path(by_name["s3"].path).parent.name == "deeper"


def test_scan_keeps_the_first_duplicate_and_counts_the_rest(tmp_path: Path) -> None:
    make_images(tmp_path / "b_copy", ["s1_rgb_01_01.png", "s1_rgb_01_02.png"])
    make_images(tmp_path / "a_original", ["s1_rgb_01_01.png"])
    make_images(tmp_path / "c_copy", ["s1_rgb_01_01.png"])

    scan = scan_image_folder(str(tmp_path))

    assert [(r.name, r.row, r.node) for r in scan.records] == [("s1", 1, 1), ("s1", 1, 2)]
    # walk order is sorted, so 'a_original' wins over 'b_copy'/'c_copy'
    assert Path(scan.records[0].path).parent.name == "a_original"
    assert scan.duplicate_count == 2
    assert sorted(Path(path).parent.name for path in scan.duplicate_paths) == [
        "b_copy",
        "c_copy",
    ]
    assert scan.folder_count == 3


def test_scan_is_deterministic(tmp_path: Path) -> None:
    for folder in ("z_last", "m_middle", "a_first"):
        make_images(tmp_path / folder, ["s_rgb_01_01.png"])

    first = scan_image_folder(str(tmp_path))
    second = scan_image_folder(str(tmp_path))

    assert [r.path for r in first.records] == [r.path for r in second.records]
    assert first.duplicate_paths == second.duplicate_paths
    assert Path(first.records[0].path).parent.name == "a_first"


def test_scan_of_an_empty_tree(tmp_path: Path) -> None:
    make_images(tmp_path / "empty", ["readme.txt"])
    scan = scan_image_folder(str(tmp_path))
    assert (scan.count, scan.duplicate_count, scan.folder_count) == (0, 0, 0)
    assert len(scan) == 0


def test_store_load_folder_returns_the_scan_result(tmp_path: Path) -> None:
    make_images(tmp_path / "sub_a", ["s1_rgb_01_01.png", "s1_rgb_01_02.png"])
    make_images(tmp_path / "sub_b", ["s2_rgb_01_01.png", "s1_rgb_01_01.png"])

    store = ImageStore()
    scan = store.load_folder(str(tmp_path))

    assert scan.count == 3
    assert scan.duplicate_count == 1
    assert len(store) == 3
    assert store.current_record is store.records[0]
    assert store.name_counts() == [("s1", 2), ("s2", 1)]


@pytest.mark.parametrize(
    "raw, expected",
    [("01", 1), (1, 1), (1.0, 1), ("  7 ", 7), ("", None), (None, None), ("x", None), (1.5, None)],
)
def test_normalize_int(raw, expected):
    assert normalize_int(raw) == expected


@pytest.mark.parametrize(
    "raw, expected",
    [(None, None), ("", None), ("   ", None), ("  Pass ", "Pass"), ("Weird", "Weird"), (3, "3")],
)
def test_normalize_status(raw, expected):
    assert normalize_status(raw) == expected


def test_status_display_uses_blank_marker():
    assert status_display(None) == BLANK_DISPLAY
    assert status_display("") == BLANK_DISPLAY
    assert status_display("Pass") == "Pass"


@pytest.mark.parametrize(
    "value, expected",
    [
        (None, ""),
        (0.0, "0"),
        (1.018096e-07, "1.018e-07"),
        (0.0008, "8.000e-04"),
        (-0.0005, "-5.000e-04"),
        (0.001, "0.001"),
        (3.77, "3.77"),
        (13.88724, "13.89"),
        (1234.5, "1234"),
        (99999.0, "1e+05"),  # below 1e5 -> 4 significant digits
        (123456.0, "1.235e+05"),  # at/above 1e5 -> scientific
        ("0.0002", "2.000e-04"),  # numeric text is accepted too
    ],
)
def test_format_metric(value, expected):
    assert format_metric(value) == expected


# --------------------------------------------------------------------------- #
# Records
# --------------------------------------------------------------------------- #

def test_set_status_marks_dirty_only_on_change() -> None:
    record = ImageRecord(name="s", row=1, node=1, status="Pass")

    assert record.set_status("Pass") is False
    assert record.dirty is False

    assert record.set_status("No Active") is True
    assert record.status == "No Active"
    assert record.dirty is True

    record.commit_status()  # as if the record had just been saved
    assert record.dirty is False

    assert record.set_status("   ") is True  # blank clears the cell
    assert record.status is None
    assert record.status_text == ""
    assert record.dirty is True


# --------------------------------------------------------------------------- #
# original_status / value based dirty
# --------------------------------------------------------------------------- #

def test_a_freshly_scanned_record_has_no_original_status() -> None:
    record = ImageRecord(name="s", row=1, node=1)
    assert record.status is None
    assert record.original_status is None
    assert record.dirty is False


def test_dirty_is_derived_from_the_value_not_a_flag() -> None:
    record = ImageRecord(name="s", row=1, node=1)
    record.load_status("Pass")
    assert (record.status, record.original_status, record.dirty) == ("Pass", "Pass", False)

    record.set_status(STATUS_OPEN)
    assert record.dirty is True

    # retyping the original value heals the record without any explicit reset
    record.set_status("Pass")
    assert record.dirty is False


def test_revert_status_restores_the_original_value() -> None:
    record = ImageRecord(name="s", row=1, node=1)
    record.load_status("No Gate Effect")

    record.set_status(STATUS_OPEN)
    assert record.dirty is True

    assert record.revert_status() is True
    assert record.status == "No Gate Effect"
    assert record.dirty is False
    # already on the original value -> nothing changes
    assert record.revert_status() is False


def test_revert_restores_a_blank_original() -> None:
    record = ImageRecord(name="s", row=1, node=1)  # never seen in a data file
    record.set_status(STATUS_OPEN)
    assert record.dirty is True

    assert record.revert_status() is True
    assert record.status is None
    assert record.status_text == ""
    assert record.dirty is False


def test_blank_and_whitespace_originals_count_as_equal() -> None:
    record = ImageRecord(name="s", row=1, node=1, status="   ", original_status="")
    assert (record.status, record.original_status) == (None, None)
    assert record.dirty is False


def test_commit_status_moves_the_revert_target_to_the_saved_value() -> None:
    record = ImageRecord(name="s", row=1, node=1)
    record.load_status("Pass")

    record.set_status(STATUS_OPEN)
    record.commit_status()  # saved: the file now holds 'Open'
    assert record.dirty is False

    record.set_status(STATUS_NO_ACTIVE)
    assert record.dirty is True
    record.revert_status()
    # back to the SAVED value, not to the value loaded at session start
    assert record.status == STATUS_OPEN
    assert record.dirty is False


def test_can_write_back_requires_worksheet_coordinates() -> None:
    record = ImageRecord(name="s", row=1, node=1)
    assert record.can_write_back is False
    record.excel_row, record.excel_status_col = 5, 10
    assert record.can_write_back is True
    assert record.key == (1, 1)


# --------------------------------------------------------------------------- #
# Statuses / counts
# --------------------------------------------------------------------------- #

def test_unique_statuses_are_dynamic_with_blank_last() -> None:
    store = make_store(["Pass", None, "Weird Status", "No Active", "Pass"])
    assert store.unique_statuses() == ["No Active", "Pass", "Weird Status", None]


def test_status_counts_full_and_filtered() -> None:
    store = make_store(["Pass", "No Active", "Pass", None, "Pass"])
    assert store.status_counts() == {"Pass": 3, "No Active": 1, None: 1}

    store.set_filter(["Pass", None])
    assert store.status_counts(store.visible()) == {"Pass": 3, None: 1}
    assert store.status_counts() == {"Pass": 3, "No Active": 1, None: 1}


# --------------------------------------------------------------------------- #
# Filtering
# --------------------------------------------------------------------------- #

def test_filter_hides_rows() -> None:
    store = make_store(["Pass", "No Active", "Pass", None, "Pass"])
    assert store.visible_count == 5
    assert store.filter_active is False

    store.set_filter(["Pass"])
    assert store.filter_active is True
    assert [record.node for record in store.visible()] == [1, 3, 5]
    assert store.filter_description() == "Pass"

    store.set_filter(["No Active", None])
    assert store.filter_description() == "No Active, %s" % BLANK_DISPLAY

    store.set_filter([])
    assert store.visible_count == 0

    store.set_filter(None)
    assert store.visible_count == 5
    assert store.filter_active is False


def test_filter_covering_every_value_is_not_active() -> None:
    store = make_store(["Pass", None])
    store.set_filter(["Pass", None])
    assert store.filter_active is False
    assert store.filter_description() == ""


def test_ensure_current_visible_moves_to_next_then_previous() -> None:
    store = make_store(["Pass", "No Active", "Pass", None, "Pass"])
    records = store.records

    store.current_record = records[1]
    store.set_filter(["Pass"])
    assert store.ensure_current_visible() is records[2]  # next visible row

    store.current_record = records[4]
    store.set_filter(["No Active"])
    assert store.ensure_current_visible() is records[1]  # previous visible row

    store.set_filter([])
    assert store.ensure_current_visible() is None
    assert store.current_index == -1


def test_status_edit_reapplies_the_filter() -> None:
    store = make_store(["Pass", "No Active", "Pass"])
    store.set_filter(["No Active"])
    store.current_record = store.records[1]
    assert store.visible_count == 1

    store.apply_status([store.records[1]], STATUS_PASS)

    assert store.visible_count == 0
    assert store.ensure_current_visible() is None


# --------------------------------------------------------------------------- #
# Navigation
# --------------------------------------------------------------------------- #

def test_navigation_operates_on_the_filtered_list() -> None:
    store = make_store(["Pass", "No Active", "Pass", None, "Pass"])
    records = store.records
    store.set_filter(["Pass"])
    store.set_current_index(0)

    assert store.current_index == 0
    assert store.navigate(1) is records[2]
    assert store.current_index == 1
    assert store.navigate(100) is records[4]  # clamped to the last visible row
    assert store.current_index == 2
    assert store.navigate(-100) is records[0]
    assert store.current_index == 0
    assert store.navigate(-1) is records[0]


def test_navigation_on_an_empty_store() -> None:
    store = ImageStore()
    assert store.navigate(1) is None
    assert store.current_index == -1
    assert store.record_at(0) is None


# --------------------------------------------------------------------------- #
# Sorting
# --------------------------------------------------------------------------- #

def test_sort_toggles_direction_and_keeps_the_current_record() -> None:
    store = ImageStore(
        [
            ImageRecord(name="s", row=1, node=3, status="Pass"),
            ImageRecord(name="s", row=1, node=1, status=None),
            ImageRecord(name="s", row=1, node=2, status="No Active"),
        ]
    )
    current = store.records[0]  # node 3
    store.current_record = current
    assert store.current_index == 0

    assert store.sort_by("node") is False
    assert [record.node for record in store.records] == [1, 2, 3]
    # the selection still points at the item the user was looking at
    assert store.current_record is current
    assert store.current_index == 2

    assert store.sort_by("node") is True
    assert [record.node for record in store.records] == [3, 2, 1]
    assert store.current_record is current
    assert store.current_index == 0


def test_sort_by_status_puts_blanks_last() -> None:
    store = make_store(["Pass", None, "No Active"])
    store.sort_by("status")
    assert [record.status for record in store.records] == ["No Active", "Pass", None]


def test_sort_by_metric_puts_missing_values_last() -> None:
    store = make_store(["Pass", "Pass", "Pass"])
    store.records[0].metrics = {"ON": 5.0}
    store.records[1].metrics = {"ON": None}
    store.records[2].metrics = {"ON": 1.0}

    store.sort_by("ON")
    assert [record.metrics.get("ON") for record in store.records] == [1.0, 5.0, None]


def test_sort_by_unknown_column_raises() -> None:
    with pytest.raises(KeyError):
        make_store(["Pass"]).sort_by("nope")


# --------------------------------------------------------------------------- #
# Dirty tracking
# --------------------------------------------------------------------------- #

def test_apply_status_returns_changed_records_and_marks_them_dirty() -> None:
    store = make_store(["Pass", "No Active", "Pass"])
    changed = store.apply_status(store.records, STATUS_PASS)

    assert changed == [store.records[1]]  # the two 'Pass' rows did not change
    assert store.dirty_count == 1
    assert [record.dirty for record in store.records] == [False, True, False]

    store.clear_dirty()
    assert store.dirty_count == 0
    assert store.dirty_records() == []


def test_apply_status_can_clear_a_status() -> None:
    store = make_store(["Pass"])
    assert store.apply_status(store.records, None) == [store.records[0]]
    assert store.records[0].status is None
    assert store.records[0].dirty is True


def test_clear_dirty_for_a_subset() -> None:
    store = make_store(["Pass", "Pass"])
    store.apply_status(store.records, STATUS_NO_ACTIVE)
    assert store.dirty_count == 2

    store.clear_dirty([store.records[0]])
    assert store.dirty_count == 1
    assert store.dirty_records() == [store.records[1]]


def test_store_revert_status_restores_originals_and_clears_dirty() -> None:
    store = make_store(["Pass", "No Active", None])
    store.apply_status(store.records, STATUS_OPEN)
    assert store.dirty_count == 3

    changed = store.revert_status(store.records)

    assert changed == store.records
    assert [record.status for record in store.records] == ["Pass", "No Active", None]
    assert store.dirty_count == 0
    assert store.dirty_records() == []
    # nothing left to revert
    assert store.revert_status(store.records) == []


def test_store_revert_status_touches_only_the_given_records() -> None:
    store = make_store(["Pass", "Pass"])
    store.apply_status(store.records, STATUS_OPEN)

    changed = store.revert_status([store.records[0]])

    assert changed == [store.records[0]]
    assert store.records[0].status == "Pass"
    assert store.records[1].status == STATUS_OPEN
    assert store.dirty_records() == [store.records[1]]


def test_revert_reapplies_the_filter() -> None:
    """A reverted row leaves a filtered view just like an edited one."""
    store = make_store(["Pass", "Pass"])
    store.apply_status([store.records[0]], STATUS_OPEN)
    store.set_filter([STATUS_OPEN])
    assert store.visible_count == 1

    store.revert_status([store.records[0]])
    assert store.visible_count == 0


def test_manually_retyping_the_original_value_clears_the_dirty_state() -> None:
    store = make_store(["Pass", "No Active"])
    store.apply_status([store.records[0]], STATUS_OPEN)
    assert store.dirty_count == 1

    store.apply_status([store.records[0]], STATUS_PASS)

    assert store.dirty_count == 0
    assert store.dirty_records() == []


# --------------------------------------------------------------------------- #
# CSV join / store housekeeping
# --------------------------------------------------------------------------- #

def test_apply_csv_labels_matches_on_name_row_node() -> None:
    store = ImageStore(
        [
            ImageRecord(name="s", row=1, node=1),
            ImageRecord(name="s", row=1, node=2),
        ]
    )
    matched = store.apply_csv_labels(
        {("s", 1, 1): "Pass"}, {("s", 1, 1): {"note": "ok"}}
    )

    assert matched == 1
    assert store.records[0].status == "Pass"
    assert store.records[0].extra_fields == {"note": "ok"}
    assert store.records[0].no_data is False
    assert store.records[1].status is None
    assert store.records[1].no_data is True


def test_apply_csv_labels_captures_the_original_status() -> None:
    store = ImageStore(
        [
            ImageRecord(name="s", row=1, node=1),
            ImageRecord(name="s", row=1, node=2),
        ]
    )
    store.apply_csv_labels({("s", 1, 1): "Pass", ("s", 1, 2): None})

    loaded, blank = store.records
    assert (loaded.status, loaded.original_status) == ("Pass", "Pass")
    assert (blank.status, blank.original_status) == (None, None)
    assert store.dirty_count == 0

    # an edit is undone by reverting to the label the CSV held
    store.apply_status([loaded], STATUS_OPEN)
    assert store.dirty_records() == [loaded]
    store.revert_status([loaded])
    assert loaded.status == "Pass"
    assert store.dirty_count == 0


def test_set_records_resets_filter_sort_and_current() -> None:
    store = make_store(["Pass", "No Active"])
    store.set_filter(["Pass"])
    store.sort_by("node")

    store.set_records([ImageRecord(name="x", row=2, node=2, status=None)])

    assert len(store) == 1
    assert store.filter_values is None
    assert store.sort_state == (None, False)
    assert store.current_record is store.records[0]

    store.clear()
    assert len(store) == 0
    assert store.current_record is None
