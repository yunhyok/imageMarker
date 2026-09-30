"""Head-less smoke test of the tkinter UI (skipped when no display is available).

Runs the main window against a temporary image folder and drives it the way
the keyboard would: label keys of the active set, digit ordinals, clearing,
switching presets and applying a custom set.  Everything tkinter-related is
exercised once so a broken widget or binding fails here instead of in front
of the user.
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

tk = pytest.importorskip("tkinter")
pytest.importorskip("PIL")

from imagemarker.label_sets import AppConfig, LabelDef, LabelSet  # noqa: E402


@pytest.fixture
def root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("IMAGEMARKER_CONFIG_DIR", str(tmp_path / "config"))
    try:
        window = tk.Tk()
    except tk.TclError as exc:  # no display
        pytest.skip("no display available: %s" % exc)
    window.withdraw()
    yield window
    try:
        window.destroy()
    except tk.TclError:
        pass


@pytest.fixture
def image_folder(tmp_path: Path) -> Path:
    from PIL import Image

    folder = tmp_path / "images"
    folder.mkdir()
    for row in range(1, 3):
        for node in range(1, 4):
            Image.new("RGB", (20, 20), (row * 60, node * 60, 90)).save(
                folder / ("sam1_rgb_%02d_%02d.png" % (row, node))
            )
    return folder


def _key(app, keysym: str, state: int = 0):
    return app._on_key_press(SimpleNamespace(keysym=keysym, state=state))


def _load(app, folder: Path) -> None:
    app.store.load_folder(str(folder))
    app.image_folder = str(folder)
    app.rebuild_filter_menu()
    app.update_table()
    app.load_current_image()
    app.update_info()
    app.root.update()


@pytest.mark.parametrize("with_ir", [False, True])
def test_rgb_folder_load_display_and_export(root, image_folder, tmp_path, monkeypatch, with_ir):
    """One RGB per device works with no partner; obsolete IR is never decoded."""
    import csv
    from imagemarker import app as ui

    if with_ir:
        (image_folder / "sam1_ir_01_01.png").write_bytes(b"not an image")
        infrared = image_folder / "infrared"
        infrared.mkdir()
        (infrared / "sam2_ir_01_01.png").write_bytes(b"not an image")
    monkeypatch.setattr(ui.filedialog, "askdirectory", lambda **kwargs: str(image_folder))
    monkeypatch.setattr(ui.messagebox, "showinfo", lambda *args, **kwargs: None)
    app = ui.ImageMarkerApp(root, AppConfig())
    # Map transparently so Tk lays out the real full-width image pane.
    root.attributes("-alpha", 0.0)
    root.deiconify()
    root.update()
    app.load_folder()
    root.update_idletasks()
    app.display_image()

    assert len(app.store.records) == 6
    assert len(app.tree.get_children()) == 6
    assert app._rgb_image.getpixel((0, 0)) == (60, 60, 90)
    assert app.rgb_canvas.winfo_width() > 100
    assert app.rgb_canvas.winfo_width() == app.image_frame.winfo_width()
    assert app.image_frame.winfo_children() == [app.rgb_canvas]
    assert sum(app.rgb_canvas.type(item) == "image" for item in app.rgb_canvas.find_all()) == 1
    _key(app, "g")
    app.navigate(1)
    assert app._rgb_image.getpixel((0, 0)) == (60, 120, 90)
    _key(app, "b")

    output = tmp_path / "labels.csv"
    monkeypatch.setattr(ui.filedialog, "asksaveasfilename", lambda **kwargs: str(output))
    assert app.save_csv()
    with output.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 6
    assert [row["label"] for row in rows[:2]] == ["GOOD", "BAD"]
    assert {row["name"] for row in rows} == {"sam1"}


@pytest.mark.parametrize("selection", ["empty", "ir_only", "cancel", "read_error", "decline"])
def test_rejected_folder_keeps_current_session(root, image_folder, tmp_path, monkeypatch, selection):
    from imagemarker import app as ui

    app = ui.ImageMarkerApp(root, AppConfig())
    _load(app, image_folder)
    _key(app, "g")
    record = app.store.current_record
    app.source_path = "existing.csv"
    before = (list(app.store.records), app.tree.get_children(), app._rgb_image,
              app.image_folder, app.source_path, app.info_label.cget("text"))
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    if selection == "ir_only":
        (candidate / "sam1_ir_01_01.png").write_bytes(b"obsolete IR")
    elif selection == "decline":
        candidate = image_folder
    monkeypatch.setattr(ui.filedialog, "askdirectory",
                        lambda **kwargs: "" if selection == "cancel" else str(candidate))
    messages = []
    for kind in ("showwarning", "showerror"):
        monkeypatch.setattr(ui.messagebox, kind, lambda *args, **kwargs: messages.append(args))
    confirmations = []
    monkeypatch.setattr(app, "confirm_discard_changes", lambda action: confirmations.append(action) or False)
    if selection == "read_error":
        def fail_scan(folder):
            raise OSError("unreadable")
        monkeypatch.setattr(ui, "scan_image_folder", fail_scan)

    app.load_folder()

    assert (list(app.store.records), app.tree.get_children(), app._rgb_image,
            app.image_folder, app.source_path, app.info_label.cget("text")) == before
    assert app.store.current_record is record
    assert record.status == "GOOD" and record.dirty
    assert bool(confirmations) == (selection == "decline")
    assert bool(messages) == (selection in {"empty", "ir_only", "read_error"})


def test_default_set_hotkeys_and_ordinals(root, image_folder: Path):
    from imagemarker.app import ImageMarkerApp

    app = ImageMarkerApp(root, AppConfig())
    _load(app, image_folder)

    assert app.label_set.names == ["GOOD", "BAD", "OPEN"]
    assert [button.cget("text") for button in app._label_buttons] == [
        "GOOD  [G/1]", "BAD  [B/2]", "OPEN  [O/3]",
    ]

    assert _key(app, "g") == "break"
    app.navigate(1)
    assert _key(app, "B") == "break"          # letters are case-insensitive
    app.navigate(1)
    assert _key(app, "3") == "break"          # digit ordinal
    app.navigate(1)
    assert _key(app, "x") is None             # unbound key is left alone
    assert _key(app, "Up") is None            # navigation keys are not swallowed
    assert _key(app, "o", state=0x4) is None  # Ctrl+O is a file shortcut

    assert [record.status for record in app.store.records] == [
        "GOOD", "BAD", "OPEN", None, None, None,
    ]
    assert app.store.dirty_count == 3

    _key(app, "0")
    assert app.store.current_record.status is None
    app.navigate(-1)
    _key(app, "Delete")
    assert app.store.records[2].status is None


def test_switching_presets_and_custom_set(root, image_folder: Path, tmp_path: Path):
    from imagemarker.app import ImageMarkerApp

    app = ImageMarkerApp(root, AppConfig())
    _load(app, image_folder)

    app.use_preset("Electrical (legacy 1.x)")
    root.update()
    assert len(app._label_buttons) == 5
    assert app._label_set_var.get() == "preset:Electrical (legacy 1.x)"
    _key(app, "Right")
    assert app.store.current_record.status == "Open"

    custom = LabelSet("Mine", [LabelDef("YES", "#00aa00", ["y"]), LabelDef("NO", "#aa0000", ["n"])])
    app.apply_label_set(custom)
    root.update()
    assert app._label_set_var.get() == "custom"
    assert app.hint_label.cget("text").startswith("YES (Y/1)  NO (N/2)")
    _key(app, "n")
    assert app.store.current_record.status == "NO"

    # The active set is persisted for the next session.
    saved = AppConfig.load(str(tmp_path / "config" / "config.json"))
    assert saved.label_set.names == ["YES", "NO"]


def test_auto_advance_moves_to_next_row(root, image_folder: Path):
    from imagemarker.app import ImageMarkerApp

    app = ImageMarkerApp(root, AppConfig(auto_advance=True))
    _load(app, image_folder)
    assert app.store.current_index == 0
    _key(app, "g")
    assert app.store.current_index == 1
    _key(app, "g")
    assert app.store.current_index == 2
    assert [record.status for record in app.store.records[:3]] == ["GOOD", "GOOD", None]


def test_canonical_spelling_is_applied(root, image_folder: Path):
    from imagemarker.app import ImageMarkerApp

    app = ImageMarkerApp(root, AppConfig())
    _load(app, image_folder)
    app.set_status("good")
    assert app.store.current_record.status == "GOOD"
    app.set_status("Something else")
    assert app.store.current_record.status == "Something else"


def test_label_set_dialog_round_trip(root):
    from imagemarker.label_dialogs import LabelSetDialog

    dialog = LabelSetDialog(root, LabelSet("Base", [LabelDef("A", "#111111", ["a"])]))
    root.update()
    dialog._add_label()
    dialog.label_name_var.set("B")
    dialog._move(-1)
    dialog.name_var.set("Edited")
    dialog._on_ok()
    root.update()
    assert dialog.result is not None
    assert dialog.result.name == "Edited"
    assert dialog.result.names == ["B", "A"]


def test_label_set_dialog_rejects_invalid(root, monkeypatch: pytest.MonkeyPatch):
    from imagemarker import label_dialogs

    errors = []
    monkeypatch.setattr(
        label_dialogs.messagebox, "showerror", lambda *args, **kwargs: errors.append(args)
    )
    dialog = label_dialogs.LabelSetDialog(root, LabelSet("Base", [LabelDef("A", "#111111", ["a"])]))
    root.update()
    dialog._add_label()
    dialog.label_name_var.set("a")  # duplicate (case-insensitive)
    dialog._on_ok()
    assert errors and dialog.result is None
    dialog.destroy()
