"""Configurable label sets for ImageMarker.

A *label set* is an ordered list of labels, each with a display name (the
string written to the ``Status`` column), a colour and any number of hotkeys.
The application ships three presets (GOOD / BAD / OPEN is the default since
v2.0) and lets the user edit, import and export sets from the ``Labels`` menu.
The active set is remembered between sessions in a small JSON config file.

This module is GUI free (no tkinter) so it can be unit tested head-lessly.
"""

from __future__ import annotations

import json
import os
import re
import sys
from dataclasses import dataclass, field, replace
from typing import Any, Dict, List, Mapping, Optional, Tuple

SCHEMA_VERSION = 1

#: Maximum number of labels in one set (keeps the label bar and the hint line
#: readable; digit shortcuts 1..9 also stop making sense beyond this).
MAX_LABELS = 9

#: Key symbols the main window uses for navigation / editing; a label may not
#: claim one of these.  Stored in tkinter ``keysym`` spelling.
RESERVED_KEYS: Tuple[str, ...] = (
    "Up", "Down", "Prior", "Next",  # navigation
    "Left",                          # revert to source label
    "Delete", "0",                   # clear label
    "Escape", "Return", "Tab", "space", "BackSpace",
)

#: Friendly names for the hint line / label bar.
KEY_DISPLAY: Dict[str, str] = {
    "Right": "→",
    "Left": "←",
    "Up": "↑",
    "Down": "↓",
    "Prior": "PgUp",
    "Next": "PgDn",
    "Delete": "Del",
    "space": "Space",
    "Return": "Enter",
    "BackSpace": "Bksp",
    "Insert": "Ins",
    "Home": "Home",
    "End": "End",
    "plus": "+",
    "minus": "-",
    "period": ".",
    "comma": ",",
    "slash": "/",
    "semicolon": ";",
    "bracketleft": "[",
    "bracketright": "]",
}

_HEX_COLOR = re.compile(r"^#[0-9A-Fa-f]{6}$")


# --------------------------------------------------------------------------- #
# Colours
# --------------------------------------------------------------------------- #

def parse_hex(color: str) -> Tuple[int, int, int]:
    color = color.strip()
    if not _HEX_COLOR.match(color):
        raise ValueError(f"colour must be #RRGGBB, got {color!r}")
    return int(color[1:3], 16), int(color[3:5], 16), int(color[5:7], 16)


def blend_with_white(color: str, amount: float = 0.72) -> str:
    """Lighten ``color`` towards white; ``amount`` 0 = unchanged, 1 = white.

    Used for table row backgrounds so black text stays readable on top of
    strongly saturated label colours.
    """
    r, g, b = parse_hex(color)
    amount = max(0.0, min(1.0, amount))
    r = round(r + (255 - r) * amount)
    g = round(g + (255 - g) * amount)
    b = round(b + (255 - b) * amount)
    return "#%02x%02x%02x" % (r, g, b)


def is_dark(color: str) -> bool:
    """``True`` when white text reads better on ``color`` than black."""
    r, g, b = parse_hex(color)
    luminance = 0.299 * r + 0.587 * g + 0.114 * b
    return luminance < 150


# --------------------------------------------------------------------------- #
# Keys
# --------------------------------------------------------------------------- #

def normalize_key(key: Any) -> str:
    """Canonical tkinter keysym spelling for a user-entered key.

    Single letters are stored lower-case (matching is case-insensitive so the
    key works with Caps Lock or Shift as well); everything else is kept as
    typed after trimming.  Returns ``""`` for blank input.
    """
    if key is None:
        return ""
    text = str(key).strip()
    if not text:
        return ""
    if len(text) == 1:
        if text.isalpha():
            return text.lower()
        return text
    aliases = {
        "right": "Right", "left": "Left", "up": "Up", "down": "Down",
        "pgup": "Prior", "pageup": "Prior", "prior": "Prior",
        "pgdn": "Next", "pagedown": "Next", "next": "Next",
        "del": "Delete", "delete": "Delete", "ins": "Insert", "insert": "Insert",
        "space": "space", "enter": "Return", "return": "Return",
        "backspace": "BackSpace", "esc": "Escape", "escape": "Escape",
        "home": "Home", "end": "End", "tab": "Tab",
    }
    lowered = text.lower()
    if lowered in aliases:
        return aliases[lowered]
    if re.fullmatch(r"[fF]([1-9]|1[0-2])", text):
        return "F" + text[1:]
    return text


def key_display(key: str) -> str:
    """Short human readable form of a keysym for hints and buttons."""
    if not key:
        return ""
    if key in KEY_DISPLAY:
        return KEY_DISPLAY[key]
    if len(key) == 1:
        return key.upper()
    return key


def keysym_matches(event_keysym: str, key: str) -> bool:
    """Compare a tkinter ``event.keysym`` with a stored key (letters ignore case)."""
    if not key or not event_keysym:
        return False
    if len(key) == 1 and key.isalpha() and len(event_keysym) == 1:
        return event_keysym.lower() == key.lower()
    return event_keysym == key


# --------------------------------------------------------------------------- #
# Model
# --------------------------------------------------------------------------- #

@dataclass
class LabelDef:
    """One label: the ``Status`` string it writes, its colour and hotkeys."""

    name: str
    color: str = "#9e9e9e"
    keys: List[str] = field(default_factory=list)
    description: str = ""

    def __post_init__(self) -> None:
        self.name = str(self.name).strip()
        self.color = str(self.color).strip()
        self.keys = [k for k in (normalize_key(key) for key in self.keys) if k]
        self.description = str(self.description or "").strip()

    @property
    def row_color(self) -> str:
        """Pale version of :attr:`color` for table row backgrounds."""
        try:
            return blend_with_white(self.color)
        except ValueError:
            return "white"

    @property
    def key_hint(self) -> str:
        return "/".join(key_display(key) for key in self.keys)

    def to_dict(self) -> Dict[str, Any]:
        data: Dict[str, Any] = {"name": self.name, "color": self.color, "keys": list(self.keys)}
        if self.description:
            data["description"] = self.description
        return data

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "LabelDef":
        keys = data.get("keys")
        if keys is None and data.get("key"):
            keys = [data["key"]]
        if isinstance(keys, str):
            keys = [keys]
        return cls(
            name=str(data.get("name", "")),
            color=str(data.get("color", "#9e9e9e")),
            keys=list(keys or []),
            description=str(data.get("description", "") or ""),
        )


@dataclass
class LabelSet:
    """An ordered, validated collection of :class:`LabelDef`."""

    name: str
    labels: List[LabelDef] = field(default_factory=list)
    #: ``True`` for the built-in presets (they cannot be edited in place).
    preset: bool = False

    # -- lookup ------------------------------------------------------------ #

    def find(self, status: Optional[str]) -> Optional[LabelDef]:
        """Label whose name equals ``status`` (case-insensitive), or ``None``."""
        if status is None:
            return None
        wanted = str(status).strip().casefold()
        for label in self.labels:
            if label.name.casefold() == wanted:
                return label
        return None

    def canonical(self, status: Optional[str]) -> Optional[str]:
        """``status`` spelled the way this set spells it; unknown values pass through."""
        label = self.find(status)
        return label.name if label is not None else status

    def by_key(self, keysym: str, digit_ordinals: bool = True) -> Optional[LabelDef]:
        """Label bound to ``keysym``; digits ``1..9`` fall back to ordinals."""
        for label in self.labels:
            if any(keysym_matches(keysym, key) for key in label.keys):
                return label
        if digit_ordinals and len(keysym) == 1 and keysym.isdigit():
            index = int(keysym) - 1
            if 0 <= index < len(self.labels):
                return self.labels[index]
        return None

    def color_for(self, status: Optional[str], default: str = "white") -> str:
        label = self.find(status)
        return label.row_color if label is not None else default

    def overlay_color_for(self, status: Optional[str], default: str = "white") -> str:
        label = self.find(status)
        return label.color if label is not None else default

    @property
    def names(self) -> List[str]:
        return [label.name for label in self.labels]

    def hint_text(self, digit_ordinals: bool = True) -> str:
        """``'GOOD (G/1)  BAD (B/2)  OPEN (O/3)'`` for the hint line."""
        parts = []
        for index, label in enumerate(self.labels, start=1):
            keys = [key_display(key) for key in label.keys]
            if digit_ordinals and index <= 9 and str(index) not in label.keys:
                keys.append(str(index))
            parts.append("%s (%s)" % (label.name, "/".join(keys)) if keys else label.name)
        return "  ".join(parts)

    # -- validation ---------------------------------------------------------- #

    def validate(self) -> List[str]:
        """Return a list of problems (empty when the set is usable)."""
        problems: List[str] = []
        if not self.name.strip():
            problems.append("The label set needs a name.")
        if not 1 <= len(self.labels) <= MAX_LABELS:
            problems.append("A label set needs between 1 and %d labels." % MAX_LABELS)
        seen_names: Dict[str, int] = {}
        seen_keys: Dict[str, str] = {}
        for index, label in enumerate(self.labels, start=1):
            if not label.name:
                problems.append("Label #%d has no name." % index)
            elif "\n" in label.name or "\r" in label.name:
                problems.append("Label #%d: the name may not contain line breaks." % index)
            else:
                folded = label.name.casefold()
                if folded in seen_names:
                    problems.append(
                        "Label '%s' appears more than once (names are compared "
                        "case-insensitively)." % label.name
                    )
                seen_names[folded] = index
            try:
                parse_hex(label.color)
            except ValueError:
                problems.append("Label '%s': colour '%s' must be #RRGGBB." % (label.name, label.color))
            for key in label.keys:
                if key in RESERVED_KEYS:
                    problems.append(
                        "Label '%s': key '%s' is reserved for navigation or clearing."
                        % (label.name, key_display(key))
                    )
                    continue
                owner = seen_keys.get(key)
                if owner is not None and owner != label.name:
                    problems.append(
                        "Key '%s' is bound to both '%s' and '%s'."
                        % (key_display(key), owner, label.name)
                    )
                seen_keys[key] = label.name
        return problems

    @property
    def is_valid(self) -> bool:
        return not self.validate()

    # -- copying / serialisation ------------------------------------------ #

    def copy(self, name: Optional[str] = None, preset: bool = False) -> "LabelSet":
        return LabelSet(
            name=self.name if name is None else name,
            labels=[replace(label, keys=list(label.keys)) for label in self.labels],
            preset=preset,
        )

    def same_labels_as(self, other: "LabelSet") -> bool:
        """``True`` when both sets have identical labels (name, colour, keys, order)."""
        if len(self.labels) != len(other.labels):
            return False
        return all(
            a.name == b.name and a.color.lower() == b.color.lower() and a.keys == b.keys
            for a, b in zip(self.labels, other.labels)
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "name": self.name,
            "labels": [label.to_dict() for label in self.labels],
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any], preset: bool = False) -> "LabelSet":
        if not isinstance(data, Mapping):
            raise ValueError("label set JSON must be an object")
        labels = data.get("labels")
        if not isinstance(labels, list):
            raise ValueError("label set JSON needs a 'labels' list")
        label_set = cls(
            name=str(data.get("name", "") or "Imported"),
            labels=[LabelDef.from_dict(item) for item in labels if isinstance(item, Mapping)],
            preset=preset,
        )
        problems = label_set.validate()
        if problems:
            raise ValueError("\n".join(problems))
        return label_set

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, ensure_ascii=False) + "\n"

    @classmethod
    def from_json(cls, text: str) -> "LabelSet":
        return cls.from_dict(json.loads(text))

    def save(self, path: str) -> None:
        _atomic_write(path, self.to_json())

    @classmethod
    def load(cls, path: str) -> "LabelSet":
        with open(path, "r", encoding="utf-8-sig") as handle:
            return cls.from_json(handle.read())


# --------------------------------------------------------------------------- #
# Presets
# --------------------------------------------------------------------------- #

def preset_good_bad_open() -> LabelSet:
    """Optical inspection classes used from v2.0 on: GOOD / BAD / OPEN."""
    return LabelSet(
        "GOOD / BAD / OPEN",
        [
            LabelDef("GOOD", "#2e9e4f", ["g"], "Device looks functional"),
            LabelDef("BAD", "#d64545", ["b"], "Visible printing defect (bridging, smear, misalignment)"),
            LabelDef("OPEN", "#e8a33d", ["o"], "Electrode or channel visibly missing / disconnected"),
        ],
        preset=True,
    )


def preset_pass_fail() -> LabelSet:
    return LabelSet(
        "PASS / FAIL",
        [
            LabelDef("PASS", "#2e9e4f", ["p"], "Acceptable"),
            LabelDef("FAIL", "#d64545", ["f"], "Defective"),
        ],
        preset=True,
    )


def preset_electrical_legacy() -> LabelSet:
    """The fixed set ImageMarker 1.x shipped with (same keys, same colours)."""
    return LabelSet(
        "Electrical (legacy 1.x)",
        [
            LabelDef("Pass", "#5cc25c", ["1"]),
            LabelDef("No Active", "#4da6ff", ["2"]),
            LabelDef("No Gate Effect", "#c9b037", ["3"]),
            LabelDef("Open", "#ff6b6b", ["4", "Right"]),
            LabelDef("Short", "#ff9800", ["5"]),
        ],
        preset=True,
    )


def presets() -> List[LabelSet]:
    return [preset_good_bad_open(), preset_pass_fail(), preset_electrical_legacy()]


def default_label_set() -> LabelSet:
    return preset_good_bad_open()


def find_preset(name: str) -> Optional[LabelSet]:
    for candidate in presets():
        if candidate.name == name:
            return candidate
    return None


# --------------------------------------------------------------------------- #
# Config file
# --------------------------------------------------------------------------- #

def config_dir() -> str:
    """Per-user folder holding ``config.json`` (``%APPDATA%\\ImageMarker`` on Windows)."""
    override = os.environ.get("IMAGEMARKER_CONFIG_DIR")
    if override:
        return override
    if sys.platform.startswith("win"):
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
        return os.path.join(base, "ImageMarker")
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.join(os.path.expanduser("~"), ".config")
    return os.path.join(base, "imagemarker")


def config_path() -> str:
    return os.path.join(config_dir(), "config.json")


@dataclass
class AppConfig:
    """Everything ImageMarker remembers between sessions."""

    label_set: LabelSet = field(default_factory=default_label_set)
    #: Digit keys ``1..9`` select labels by position even without explicit keys.
    digit_ordinals: bool = True
    #: Move to the next row automatically after a label key is applied.
    auto_advance: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "label_set": self.label_set.to_dict(),
            "label_set_preset": self.label_set.name if self.label_set.preset else None,
            "digit_ordinals": bool(self.digit_ordinals),
            "auto_advance": bool(self.auto_advance),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "AppConfig":
        config = cls()
        preset_name = data.get("label_set_preset")
        preset = find_preset(preset_name) if isinstance(preset_name, str) else None
        raw = data.get("label_set")
        if preset is not None:
            config.label_set = preset
        elif isinstance(raw, Mapping):
            try:
                config.label_set = LabelSet.from_dict(raw)
            except ValueError:
                config.label_set = default_label_set()
        config.digit_ordinals = bool(data.get("digit_ordinals", True))
        config.auto_advance = bool(data.get("auto_advance", False))
        return config

    @classmethod
    def load(cls, path: Optional[str] = None) -> "AppConfig":
        """Read the config; any problem silently yields the defaults."""
        path = path or config_path()
        try:
            with open(path, "r", encoding="utf-8-sig") as handle:
                data = json.load(handle)
        except (OSError, ValueError):
            return cls()
        if not isinstance(data, Mapping):
            return cls()
        return cls.from_dict(data)

    def save(self, path: Optional[str] = None) -> None:
        path = path or config_path()
        _atomic_write(path, json.dumps(self.to_dict(), indent=2, ensure_ascii=False) + "\n")


def _atomic_write(path: str, text: str) -> None:
    directory = os.path.dirname(os.path.abspath(path))
    os.makedirs(directory, exist_ok=True)
    temp = path + ".tmp"
    with open(temp, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)
    os.replace(temp, path)


__all__ = [
    "AppConfig",
    "KEY_DISPLAY",
    "LabelDef",
    "LabelSet",
    "MAX_LABELS",
    "RESERVED_KEYS",
    "blend_with_white",
    "config_dir",
    "config_path",
    "default_label_set",
    "find_preset",
    "is_dark",
    "key_display",
    "keysym_matches",
    "normalize_key",
    "parse_hex",
    "preset_electrical_legacy",
    "preset_good_bad_open",
    "preset_pass_fail",
    "presets",
]
