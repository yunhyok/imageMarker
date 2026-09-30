"""Tests for imagemarker.label_sets and the label-set aware CSV parsing."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from imagemarker.csv_io import load_label_csv, parse_label_value  # noqa: E402
from imagemarker.label_sets import (  # noqa: E402
    MAX_LABELS,
    AppConfig,
    LabelDef,
    LabelSet,
    blend_with_white,
    default_label_set,
    find_preset,
    is_dark,
    key_display,
    keysym_matches,
    normalize_key,
    preset_electrical_legacy,
    preset_good_bad_open,
    presets,
)


# --------------------------------------------------------------------------- #
# Keys and colours
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize(
    "raw, expected",
    [
        ("G", "g"),
        ("g", "g"),
        ("1", "1"),
        (" Right ", "Right"),
        ("right", "Right"),
        ("PgUp", "Prior"),
        ("pagedown", "Next"),
        ("f5", "F5"),
        ("Del", "Delete"),
        ("", ""),
        (None, ""),
    ],
)
def test_normalize_key(raw, expected):
    assert normalize_key(raw) == expected


def test_keysym_matches_is_case_insensitive_for_letters():
    assert keysym_matches("G", "g")
    assert keysym_matches("g", "g")
    assert not keysym_matches("h", "g")
    assert keysym_matches("Right", "Right")
    assert not keysym_matches("right", "Right")
    assert not keysym_matches("g", "")


def test_key_display():
    assert key_display("g") == "G"
    assert key_display("Right") == "→"
    assert key_display("Prior") == "PgUp"
    assert key_display("F5") == "F5"


def test_colour_helpers():
    assert blend_with_white("#000000", 1.0) == "#ffffff"
    assert blend_with_white("#ff0000", 0.0) == "#ff0000"
    assert is_dark("#000000")
    assert not is_dark("#ffffff")
    with pytest.raises(ValueError):
        blend_with_white("red")


# --------------------------------------------------------------------------- #
# Presets
# --------------------------------------------------------------------------- #

def test_default_preset_is_good_bad_open():
    default = default_label_set()
    assert default.names == ["GOOD", "BAD", "OPEN"]
    assert default.preset
    assert [label.keys for label in default.labels] == [["g"], ["b"], ["o"]]


def test_all_presets_are_valid_and_findable():
    for preset in presets():
        assert preset.is_valid, preset.validate()
        assert find_preset(preset.name) is not None
        assert find_preset(preset.name).same_labels_as(preset)
    assert find_preset("does not exist") is None


def test_legacy_preset_keeps_1x_keys():
    legacy = preset_electrical_legacy()
    assert legacy.names == ["Pass", "No Active", "No Gate Effect", "Open", "Short"]
    assert legacy.by_key("4").name == "Open"
    assert legacy.by_key("Right").name == "Open"
    assert legacy.by_key("5").name == "Short"


# --------------------------------------------------------------------------- #
# Lookup
# --------------------------------------------------------------------------- #

def test_find_and_canonical_are_case_insensitive():
    label_set = preset_good_bad_open()
    assert label_set.find("good").name == "GOOD"
    assert label_set.find(" Open ").name == "OPEN"
    assert label_set.find("Pass") is None
    assert label_set.canonical("bad") == "BAD"
    assert label_set.canonical("Pass") == "Pass"
    assert label_set.canonical(None) is None


def test_by_key_uses_explicit_keys_then_digit_ordinals():
    label_set = preset_good_bad_open()
    assert label_set.by_key("g").name == "GOOD"
    assert label_set.by_key("G").name == "GOOD"
    assert label_set.by_key("2").name == "BAD"
    assert label_set.by_key("3").name == "OPEN"
    assert label_set.by_key("4") is None
    assert label_set.by_key("2", digit_ordinals=False) is None
    assert label_set.by_key("x") is None


def test_explicit_digit_key_wins_over_ordinal():
    label_set = LabelSet(
        "digits",
        [LabelDef("A", "#111111", ["2"]), LabelDef("B", "#222222", ["1"])],
    )
    assert label_set.by_key("1").name == "B"
    assert label_set.by_key("2").name == "A"


def test_colors_and_hint():
    label_set = preset_good_bad_open()
    assert label_set.overlay_color_for("good") == "#2e9e4f"
    assert label_set.color_for("GOOD") == blend_with_white("#2e9e4f")
    assert label_set.color_for("Unknown") == "white"
    assert label_set.color_for(None) == "white"
    assert label_set.hint_text() == "GOOD (G/1)  BAD (B/2)  OPEN (O/3)"
    assert label_set.hint_text(digit_ordinals=False) == "GOOD (G)  BAD (B)  OPEN (O)"


# --------------------------------------------------------------------------- #
# Validation
# --------------------------------------------------------------------------- #

def test_validate_reports_duplicates_reserved_keys_and_bad_colours():
    label_set = LabelSet(
        "bad",
        [
            LabelDef("GOOD", "#2e9e4f", ["g"]),
            LabelDef("good", "#d64545", ["g"]),
            LabelDef("", "red", ["Up"]),
        ],
    )
    problems = "\n".join(label_set.validate())
    assert "more than once" in problems
    assert "bound to both" in problems
    assert "has no name" in problems
    assert "#RRGGBB" in problems
    assert "reserved" in problems
    assert not label_set.is_valid


def test_validate_limits_label_count():
    assert LabelSet("empty", []).validate()
    too_many = LabelSet(
        "many", [LabelDef("L%d" % i, "#101010") for i in range(MAX_LABELS + 1)]
    )
    assert any("between 1 and" in problem for problem in too_many.validate())
    assert not LabelSet("one", [LabelDef("ONLY", "#101010")]).validate()


# --------------------------------------------------------------------------- #
# Copy / JSON round trip
# --------------------------------------------------------------------------- #

def test_copy_is_independent():
    original = preset_good_bad_open()
    copy = original.copy()
    copy.labels[0].keys.append("x")
    copy.labels[0].name = "CHANGED"
    assert original.labels[0].keys == ["g"]
    assert original.labels[0].name == "GOOD"
    assert not copy.preset


def test_json_round_trip(tmp_path: Path):
    label_set = LabelSet(
        "Round trip",
        [
            LabelDef("GOOD", "#2e9e4f", ["g", "F1"], "fine"),
            LabelDef("BAD", "#d64545", ["b"]),
        ],
    )
    path = tmp_path / "set.json"
    label_set.save(str(path))
    loaded = LabelSet.load(str(path))
    assert loaded.name == "Round trip"
    assert loaded.same_labels_as(label_set)
    assert loaded.labels[0].description == "fine"
    assert not loaded.preset


def test_from_dict_accepts_single_key_and_rejects_invalid():
    loaded = LabelSet.from_dict(
        {"name": "x", "labels": [{"name": "A", "color": "#000000", "key": "a"}]}
    )
    assert loaded.labels[0].keys == ["a"]
    with pytest.raises(ValueError):
        LabelSet.from_dict({"name": "x", "labels": []})
    with pytest.raises(ValueError):
        LabelSet.from_dict({"name": "x"})
    with pytest.raises(ValueError):
        LabelSet.from_json("[1, 2, 3]")


# --------------------------------------------------------------------------- #
# App config
# --------------------------------------------------------------------------- #

def test_config_defaults_when_missing(tmp_path: Path):
    config = AppConfig.load(str(tmp_path / "nope.json"))
    assert config.label_set.names == ["GOOD", "BAD", "OPEN"]
    assert config.digit_ordinals is True
    assert config.auto_advance is False


def test_config_round_trip_preset_and_custom(tmp_path: Path):
    path = tmp_path / "config.json"
    config = AppConfig(label_set=preset_electrical_legacy(), digit_ordinals=False, auto_advance=True)
    config.save(str(path))
    loaded = AppConfig.load(str(path))
    assert loaded.label_set.preset
    assert loaded.label_set.name == "Electrical (legacy 1.x)"
    assert loaded.digit_ordinals is False
    assert loaded.auto_advance is True

    custom = LabelSet("Mine", [LabelDef("YES", "#00ff00", ["y"]), LabelDef("NO", "#ff0000", ["n"])])
    AppConfig(label_set=custom).save(str(path))
    loaded = AppConfig.load(str(path))
    assert not loaded.label_set.preset
    assert loaded.label_set.names == ["YES", "NO"]


def test_config_ignores_corrupt_file(tmp_path: Path):
    path = tmp_path / "config.json"
    path.write_text("{not json", encoding="utf-8")
    assert AppConfig.load(str(path)).label_set.names == ["GOOD", "BAD", "OPEN"]
    path.write_text(json.dumps({"label_set": {"name": "x", "labels": []}}), encoding="utf-8")
    assert AppConfig.load(str(path)).label_set.names == ["GOOD", "BAD", "OPEN"]


# --------------------------------------------------------------------------- #
# CSV parsing with a label set
# --------------------------------------------------------------------------- #

def test_parse_label_value_keeps_good_with_new_set():
    label_set = preset_good_bad_open()
    assert parse_label_value("GOOD", label_set) == "GOOD"
    assert parse_label_value("good", label_set) == "GOOD"
    assert parse_label_value("open", label_set) == "OPEN"
    assert parse_label_value("Pass", label_set) == "Pass"  # verbatim, not in set
    assert parse_label_value("1", label_set) == "1"  # legacy alias not resolvable
    assert parse_label_value("None", label_set) is None
    assert parse_label_value("", label_set) is None


def test_parse_label_value_legacy_aliases_with_legacy_set():
    legacy = preset_electrical_legacy()
    assert parse_label_value("good", legacy) == "Pass"
    assert parse_label_value("1", legacy) == "Pass"
    assert parse_label_value("-1", legacy) == "Open"
    assert parse_label_value("NOACTIVE", legacy) == "No Active"
    assert parse_label_value("Weird", legacy) == "Weird"


def test_parse_label_value_without_set_is_unchanged():
    assert parse_label_value("GOOD") == "Pass"
    assert parse_label_value("1") == "Pass"
    assert parse_label_value("-1") == "Open"
    assert parse_label_value("7") is None
    assert parse_label_value("Custom") == "Custom"


def test_load_label_csv_with_label_set(tmp_path: Path):
    path = tmp_path / "labels.csv"
    path.write_text(
        "name,row,node,label\nsam,1,1,good\nsam,1,2,BAD\nsam,1,3,None\nsam,1,4,Pass\n",
        encoding="utf-8",
    )
    data = load_label_csv(str(path), preset_good_bad_open())
    assert data.labels[("sam", 1, 1)] == "GOOD"
    assert data.labels[("sam", 1, 2)] == "BAD"
    assert data.labels[("sam", 1, 3)] is None
    assert data.labels[("sam", 1, 4)] == "Pass"
