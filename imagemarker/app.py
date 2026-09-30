"""Tkinter user interface for ImageMarker.

Everything tkinter/Pillow related lives in this module; :mod:`data_model`,
:mod:`excel_io` and :mod:`csv_io` stay GUI free so they can be unit tested.
Importing this module has no side effects - no window is created until
:func:`main` runs.
"""

from __future__ import annotations

import os
import sys
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import Dict, List, Mapping, Optional, Sequence, Tuple

from PIL import Image, ImageTk

from . import __version__
from .csv_io import BASE_HEADERS, load_label_csv, save_label_csv
from .data_model import (
    BLANK_DISPLAY,
    FolderScanResult,
    ImageRecord,
    ImageStore,
    format_metric,
    status_display,
)
from .excel_io import ExcelError, ExcelFileLockedError, ExcelSource
from .label_dialogs import LabelSetDialog
from .label_sets import (
    AppConfig,
    LabelSet,
    find_preset,
    is_dark,
    key_display,
    presets,
)

APP_TITLE = "ImageMarker - RGB Viewer"

#: Fixed keys (not part of the label set).  ``Left`` reverts, these clear.
CLEAR_KEYS: Tuple[str, ...] = ("0", "Delete")
NAV_HINT = "↑↓ Navigate | Ctrl±10 | Shift±100 | PgUp/Dn±1000 | ← Revert | 0/Del Clear"

#: (column id, heading, width, anchor, sort key)
TABLE_COLUMNS: Tuple[Tuple[str, str, int, str, str], ...] = (
    ("mark", "", 26, "center", "dirty"),
    ("name", "Name", 260, "w", "name"),
    ("row", "Row", 55, "center", "row"),
    ("node", "Node", 55, "center", "node"),
    ("on", "ON", 95, "e", "ON"),
    ("off", "OFF", 95, "e", "OFF"),
    ("onoff", "ON/OFF", 80, "e", "ON/OFF"),
    ("gm", "gm", 85, "e", "gm"),
    ("vth", "Vth", 85, "e", "Vth"),
    ("mobility", "Carrier Mobility", 110, "e", "Carrier Mobility"),
    ("status", "Status", 130, "center", "status"),
)

#: Combobox entry meaning "this sample has no Excel counterpart".
SKIP_CHOICE = "(skip)"


class NameMappingDialog(tk.Toplevel):
    """Modal dialog mapping every loaded image name prefix to an Excel ``Name``.

    A recursive folder load can bring in several samples at once, so the dialog
    shows one row per image name prefix (a single-sample load simply has one
    row).  Each row is preselected with the sample-number based auto-suggestion
    and can be set to ``(skip)`` when that sample has no Excel counterpart.
    """

    def __init__(
        self,
        parent: tk.Misc,
        prefixes: Sequence[Tuple[str, int]],
        names: Sequence[Tuple[str, int]],
        suggestions: Optional[Mapping[str, Optional[str]]] = None,
    ) -> None:
        super().__init__(parent)
        self.title("Match samples to Excel names")
        self.resizable(True, True)
        self.result: Optional[Dict[str, Optional[str]]] = None
        self._prefixes = list(prefixes)
        self._names = [name for name, _ in names]
        self._choices = [SKIP_CHOICE] + [
            "%s   (%d rows)" % (name, count) for name, count in names
        ]
        self._combos: List[ttk.Combobox] = []
        suggestions = suggestions or {}

        tk.Label(
            self,
            text=(
                "Match each image sample to the Excel 'Name' that holds its "
                "data.\nRows are then joined by (Row, Node) within that Name."
            ),
            anchor="w",
            justify=tk.LEFT,
        ).pack(fill=tk.X, padx=10, pady=(10, 6))

        body = tk.Frame(self)
        body.pack(fill=tk.BOTH, expand=True, padx=10)
        for column, (heading, anchor) in enumerate(
            (("Image name prefix", "w"), ("Images", "e"), ("Excel Name", "w"))
        ):
            tk.Label(
                body, text=heading, anchor=anchor, font=("Arial", 9, "bold")
            ).grid(row=0, column=column, sticky="ew", padx=(0, 8), pady=(0, 4))
        body.grid_columnconfigure(0, weight=1)
        body.grid_columnconfigure(2, weight=1)

        suggested_count = 0
        for index, (prefix, count) in enumerate(self._prefixes, start=1):
            tk.Label(body, text=prefix, anchor="w").grid(
                row=index, column=0, sticky="ew", padx=(0, 8), pady=2
            )
            tk.Label(body, text=str(count), anchor="e").grid(
                row=index, column=1, sticky="ew", padx=(0, 8), pady=2
            )
            combo = ttk.Combobox(body, values=self._choices, state="readonly", width=44)
            suggested = suggestions.get(prefix)
            if suggested is not None and suggested in self._names:
                combo.current(self._names.index(suggested) + 1)
                suggested_count += 1
            else:
                combo.current(0)
            combo.grid(row=index, column=2, sticky="ew", pady=2)
            self._combos.append(combo)

        tk.Label(
            self,
            text="%d of %d sample(s) auto-suggested by sample number - review "
            "and adjust as needed." % (suggested_count, len(self._prefixes)),
            anchor="w",
            fg="gray30",
            font=("Arial", 8),
        ).pack(fill=tk.X, padx=10, pady=(6, 0))

        buttons = tk.Frame(self)
        buttons.pack(fill=tk.X, padx=10, pady=10)
        tk.Button(buttons, text="Cancel", width=10, command=self._on_cancel).pack(
            side=tk.RIGHT
        )
        tk.Button(buttons, text="OK", width=10, command=self._on_ok).pack(
            side=tk.RIGHT, padx=(0, 6)
        )

        self.bind("<Return>", lambda event: self._on_ok())
        self.bind("<Escape>", lambda event: self._on_cancel())
        self.protocol("WM_DELETE_WINDOW", self._on_cancel)

        self.transient(parent)
        self.update_idletasks()
        self.grab_set()
        if self._combos:
            self._combos[0].focus_set()

    def _on_ok(self) -> None:
        mapping: Dict[str, Optional[str]] = {}
        for (prefix, _), combo in zip(self._prefixes, self._combos):
            index = combo.current()
            mapping[prefix] = self._names[index - 1] if index > 0 else None
        self.result = mapping
        self.destroy()

    def _on_cancel(self) -> None:
        self.result = None
        self.destroy()


class ImageMarkerApp:
    """The main application window."""

    def __init__(self, root: tk.Tk, config: Optional[AppConfig] = None) -> None:
        self.root = root
        self.root.title(APP_TITLE)
        self.root.geometry("1400x900")

        #: Persisted preferences (active label set, digit ordinals, auto-advance).
        self.config: AppConfig = config if config is not None else AppConfig.load()
        self._label_set_var = tk.StringVar(value=self._label_set_choice_key())
        self._digit_ordinals_var = tk.BooleanVar(value=self.config.digit_ordinals)
        self._auto_advance_var = tk.BooleanVar(value=self.config.auto_advance)

        self.store = ImageStore()
        self.image_folder: Optional[str] = None
        #: Short description of the last folder scan (subfolders / duplicates).
        self.scan_summary: str = ""
        self.excel: Optional[ExcelSource] = None
        #: image name prefix -> Excel ``Name`` (``None`` = skipped by the user).
        self.excel_names: Dict[str, Optional[str]] = {}
        self.csv_headers: List[str] = list(BASE_HEADERS)
        self.source_path: Optional[str] = None

        self._rgb_image: Optional[Image.Image] = None
        self._rgb_photo: Optional[ImageTk.PhotoImage] = None
        self._overlay_job: Optional[str] = None
        self._canvas_resize_job: Optional[str] = None
        self._suspend_tree_event = False
        self._iid_to_record: Dict[str, ImageRecord] = {}
        self._record_to_iid: Dict[int, str] = {}
        self._selected_records: List[ImageRecord] = []
        self._filter_vars: Dict[str, tk.BooleanVar] = {}
        self._filter_lookup: Dict[str, Optional[str]] = {}
        self._status_tags: Dict[Optional[str], str] = {}
        self._label_buttons: List[tk.Button] = []

        self.setup_ui()
        self.bind_keys()
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.update_info()

    # ------------------------------------------------------------------ #
    # UI construction
    # ------------------------------------------------------------------ #

    def setup_ui(self) -> None:
        self._build_menu()

        # A visible, grabbable sash between the image and the table lets the
        # user trade space between the two sections freely instead of the
        # image height being fixed by a resize handler (tk.PanedWindow, not
        # ttk, so the sash is drawn and draggable).
        self.paned = tk.PanedWindow(
            self.root, orient=tk.VERTICAL, sashwidth=6, sashrelief=tk.RAISED, bg="gray50"
        )
        self.paned.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        self.image_frame = tk.Frame(self.paned, bg="gray20")
        self.paned.add(self.image_frame, minsize=120, stretch="always")

        self.rgb_canvas = tk.Canvas(self.image_frame, bg="gray40", highlightthickness=0)
        self.rgb_canvas.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        self.rgb_canvas.bind("<Configure>", self.on_canvas_resize)

        self.control_frame = tk.Frame(self.paned)
        self.paned.add(self.control_frame, minsize=180, stretch="always")

        # tk.PanedWindow has no initial-ratio option; give the image pane
        # roughly the upper half once the window has real dimensions.
        self.root.after_idle(self._set_initial_sash)

        toolbar = tk.Frame(self.control_frame)
        toolbar.pack(side=tk.TOP, fill=tk.X, padx=5, pady=5)

        tk.Button(
            toolbar,
            text="Load Folder",
            command=self.load_folder,
            font=("Arial", 10, "bold"),
            width=12,
        ).pack(side=tk.LEFT, padx=3)
        tk.Button(
            toolbar, text="Open Excel...", command=self.open_excel, font=("Arial", 10), width=12
        ).pack(side=tk.LEFT, padx=3)
        self.save_excel_button = tk.Button(
            toolbar,
            text="Save to Excel",
            command=self.save_excel,
            font=("Arial", 10, "bold"),
            width=12,
            state=tk.DISABLED,
        )
        self.save_excel_button.pack(side=tk.LEFT, padx=3)
        tk.Button(
            toolbar, text="Load CSV", command=self.load_csv, font=("Arial", 10), width=10
        ).pack(side=tk.LEFT, padx=3)
        tk.Button(
            toolbar, text="Save CSV", command=self.save_csv, font=("Arial", 10), width=10
        ).pack(side=tk.LEFT, padx=3)

        self.filter_button = tk.Menubutton(
            toolbar, text="Status filter", relief=tk.RAISED, width=14
        )
        self.filter_menu = tk.Menu(self.filter_button, tearoff=False)
        self.filter_button.config(menu=self.filter_menu)
        self.filter_button.pack(side=tk.LEFT, padx=(12, 3))
        self.rebuild_filter_menu()

        self.info_label = tk.Label(
            toolbar, text="No folder loaded", font=("Arial", 9), anchor="w"
        )
        self.info_label.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=10)

        # Label bar: one button per label of the active set (mouse alternative
        # to the hotkeys) plus revert / clear.
        self.label_bar = tk.Frame(self.control_frame)
        self.label_bar.pack(side=tk.TOP, fill=tk.X, padx=5, pady=(0, 2))

        self.hint_label = tk.Label(
            self.control_frame, text="", font=("Arial", 8), fg="blue", anchor="w"
        )
        self.hint_label.pack(side=tk.TOP, fill=tk.X, padx=5)
        self.rebuild_label_bar()

        table_frame = tk.Frame(self.control_frame)
        table_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=5, pady=5)

        vsb = ttk.Scrollbar(table_frame, orient="vertical")
        hsb = ttk.Scrollbar(table_frame, orient="horizontal")

        self.tree = ttk.Treeview(
            table_frame,
            columns=[column[0] for column in TABLE_COLUMNS],
            show="headings",
            yscrollcommand=vsb.set,
            xscrollcommand=hsb.set,
            selectmode="extended",
        )
        vsb.config(command=self.tree.yview)
        hsb.config(command=self.tree.xview)

        for column_id, heading, width, anchor, sort_key in TABLE_COLUMNS:
            self.tree.heading(
                column_id,
                text=heading,
                command=lambda key=sort_key: self.sort_column(key),
            )
            self.tree.column(column_id, width=width, anchor=anchor, stretch=False)
        self.tree.column("name", stretch=True)

        self.tree.tag_configure("dirty", font=("Arial", 9, "bold"))

        self.tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        table_frame.grid_rowconfigure(0, weight=1)
        table_frame.grid_columnconfigure(0, weight=1)

        self.tree.bind("<<TreeviewSelect>>", self.on_tree_select)

    def _set_initial_sash(self) -> None:
        """Place the sash so the image pane starts at roughly the upper half.

        ``tk.PanedWindow`` has no initial-ratio option, so this runs once the
        event loop is idle (after the window has real dimensions) and moves
        the single sash (index 0) to the vertical midpoint. If the window
        hasn't been laid out yet, retry shortly instead of placing at 0.
        """
        try:
            self.paned.update_idletasks()
            height = self.paned.winfo_height()
            if height <= 1:
                self.root.after(50, self._set_initial_sash)
                return
            self.paned.sash_place(0, 0, height // 2)
        except tk.TclError:  # window closed before this ran
            return

    def _build_menu(self) -> None:
        menubar = tk.Menu(self.root)
        file_menu = tk.Menu(menubar, tearoff=False)
        file_menu.add_command(
            label="Load Image Folder...", command=self.load_folder, accelerator="Ctrl+O"
        )
        file_menu.add_separator()
        file_menu.add_command(label="Open Excel...", command=self.open_excel)
        file_menu.add_command(
            label="Save to Excel", command=self.save_excel, accelerator="Ctrl+S"
        )
        file_menu.add_separator()
        file_menu.add_command(label="Load CSV...", command=self.load_csv)
        file_menu.add_command(label="Save CSV...", command=self.save_csv)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.on_close)
        menubar.add_cascade(label="File", menu=file_menu)

        self.labels_menu = tk.Menu(menubar, tearoff=False)
        menubar.add_cascade(label="Labels", menu=self.labels_menu)
        self.rebuild_labels_menu()

        help_menu = tk.Menu(menubar, tearoff=False)
        help_menu.add_command(label="Keyboard shortcuts", command=self._show_shortcuts)
        help_menu.add_command(label="About", command=self._show_about)
        menubar.add_cascade(label="Help", menu=help_menu)

        self.root.config(menu=menubar)
        self.file_menu = file_menu

    # ------------------------------------------------------------------ #
    # Label sets
    # ------------------------------------------------------------------ #

    @property
    def label_set(self) -> LabelSet:
        return self.config.label_set

    def _label_set_choice_key(self) -> str:
        """Radio value identifying the active set in the Labels menu."""
        return "preset:" + self.label_set.name if self.label_set.preset else "custom"

    def rebuild_labels_menu(self) -> None:
        """(Re)populate the Labels menu: presets, the custom set, editing commands."""
        menu = self.labels_menu
        menu.delete(0, tk.END)
        self._label_set_var.set(self._label_set_choice_key())
        for preset in presets():
            menu.add_radiobutton(
                label=preset.name,
                variable=self._label_set_var,
                value="preset:" + preset.name,
                command=lambda name=preset.name: self.use_preset(name),
            )
        if not self.label_set.preset:
            menu.add_radiobutton(
                label="Custom: %s" % self.label_set.name,
                variable=self._label_set_var,
                value="custom",
                state=tk.DISABLED,
            )
        menu.add_separator()
        menu.add_command(
            label="Edit label set...", command=self.edit_label_set, accelerator="Ctrl+L"
        )
        menu.add_command(label="Import label set...", command=self.import_label_set)
        menu.add_command(label="Export label set...", command=self.export_label_set)
        menu.add_separator()
        menu.add_checkbutton(
            label="Digit keys 1-9 select labels in order",
            variable=self._digit_ordinals_var,
            command=self._on_option_changed,
        )
        menu.add_checkbutton(
            label="Auto-advance to next row after labeling",
            variable=self._auto_advance_var,
            command=self._on_option_changed,
        )

    def _on_option_changed(self) -> None:
        self.config.digit_ordinals = bool(self._digit_ordinals_var.get())
        self.config.auto_advance = bool(self._auto_advance_var.get())
        self.rebuild_label_bar()
        self._save_config()

    def _save_config(self) -> None:
        try:
            self.config.save()
        except OSError as exc:
            messagebox.showwarning(
                "Settings", "Could not save the settings file:\n%s" % exc
            )

    def apply_label_set(self, label_set: LabelSet) -> None:
        """Make ``label_set`` active: menu, label bar, hint, table colours."""
        self.config.label_set = label_set
        self._status_tags = {}
        self.rebuild_labels_menu()
        self.rebuild_label_bar()
        self.update_table()
        self.update_info()
        self._save_config()

    def use_preset(self, name: str) -> None:
        preset = find_preset(name)
        if preset is not None:
            self.apply_label_set(preset)

    def edit_label_set(self) -> None:
        dialog = LabelSetDialog(self.root, self.label_set)
        self.root.wait_window(dialog)
        result = dialog.result
        if result is None:
            self._label_set_var.set(self._label_set_choice_key())
            return
        # Editing a preset without changing anything keeps it a preset.
        for preset in presets():
            if result.name == preset.name and result.same_labels_as(preset):
                self.apply_label_set(preset)
                return
        self.apply_label_set(result.copy(preset=False))

    def import_label_set(self) -> None:
        path = filedialog.askopenfilename(
            title="Import label set",
            filetypes=[("Label set JSON", "*.json"), ("All files", "*.*")],
        )
        if not path:
            return
        try:
            label_set = LabelSet.load(path)
        except (OSError, ValueError) as exc:
            messagebox.showerror("Import label set", "Could not import the label set:\n%s" % exc)
            return
        self.apply_label_set(label_set)

    def export_label_set(self) -> None:
        default_name = "".join(
            ch if ch.isalnum() or ch in "-_" else "_" for ch in self.label_set.name
        ).strip("_") or "label_set"
        path = filedialog.asksaveasfilename(
            title="Export label set",
            defaultextension=".json",
            initialfile=default_name + ".json",
            filetypes=[("Label set JSON", "*.json"), ("All files", "*.*")],
        )
        if not path:
            return
        try:
            self.label_set.save(path)
        except OSError as exc:
            messagebox.showerror("Export label set", "Could not write the file:\n%s" % exc)
            return
        messagebox.showinfo("Export label set", "Saved %s" % os.path.basename(path))

    def rebuild_label_bar(self) -> None:
        """One coloured button per label, followed by Revert and Clear."""
        for child in self.label_bar.winfo_children():
            child.destroy()
        self._label_buttons = []
        for index, label in enumerate(self.label_set.labels, start=1):
            keys = [key_display(key) for key in label.keys]
            if self.config.digit_ordinals and index <= 9 and str(index) not in label.keys:
                keys.append(str(index))
            text = label.name if not keys else "%s  [%s]" % (label.name, "/".join(keys))
            button = tk.Button(
                self.label_bar,
                text=text,
                bg=label.color,
                fg="white" if is_dark(label.color) else "black",
                activebackground=label.row_color,
                font=("Arial", 9, "bold"),
                relief=tk.RAISED,
                command=lambda value=label.name: self.set_status(value),
            )
            button.pack(side=tk.LEFT, padx=(0, 4), pady=2)
            self._label_buttons.append(button)
        tk.Button(
            self.label_bar, text="Revert  [←]", command=self.revert_status, font=("Arial", 9)
        ).pack(side=tk.LEFT, padx=(12, 4), pady=2)
        tk.Button(
            self.label_bar,
            text="Clear  [0/Del]",
            command=lambda: self.set_status(None),
            font=("Arial", 9),
        ).pack(side=tk.LEFT, padx=(0, 4), pady=2)
        tk.Label(
            self.label_bar, text="Set: %s" % self.label_set.name, font=("Arial", 8), fg="gray30"
        ).pack(side=tk.RIGHT, padx=4)
        self.hint_label.config(
            text=self.label_set.hint_text(self.config.digit_ordinals) + "   |   " + NAV_HINT
        )

    def _show_shortcuts(self) -> None:
        lines = ["Labels (active set: %s)" % self.label_set.name, ""]
        for index, label in enumerate(self.label_set.labels, start=1):
            keys = [key_display(key) for key in label.keys]
            if self.config.digit_ordinals and index <= 9 and str(index) not in label.keys:
                keys.append(str(index))
            lines.append("  %-20s %s" % (label.name, ", ".join(keys) or "(no key)"))
        lines += [
            "",
            "  Left            revert to the label in the source file",
            "  0 / Delete      clear the label",
            "",
            "Navigation",
            "  Up / Down                 move by 1",
            "  Ctrl + Up / Down          move by 10",
            "  Shift + Up / Down         move by 100",
            "  Page Up / Page Down       move by 1000",
            "",
            "File",
            "  Ctrl+O   load image folder      Ctrl+S   save to Excel",
            "  Ctrl+L   edit label set",
        ]
        messagebox.showinfo("Keyboard shortcuts", "\n".join(lines))

    def _show_about(self) -> None:
        messagebox.showinfo(
            "About ImageMarker",
            "ImageMarker %s\n\nReview RGB slice images and assign labels from a "
            "configurable label set (GOOD / BAD / OPEN by default).\nOnly the "
            "Status column of the source workbook is ever modified." % __version__,
        )

    def bind_keys(self) -> None:
        # One generic handler dispatches label keys against the active set so
        # the bindings follow the label set without re-binding.
        self.root.bind("<KeyPress>", self._on_key_press)
        self.root.bind("<Left>", lambda event: self.revert_status())
        self.root.bind("<Control-o>", lambda event: self.load_folder())
        self.root.bind("<Control-s>", lambda event: self.save_excel())
        self.root.bind("<Control-l>", lambda event: self.edit_label_set())

        self.root.bind("<Up>", lambda event: self.navigate(-1))
        self.root.bind("<Down>", lambda event: self.navigate(1))
        self.root.bind("<Control-Up>", lambda event: self.navigate(-10))
        self.root.bind("<Control-Down>", lambda event: self.navigate(10))
        self.root.bind("<Shift-Up>", lambda event: self.navigate(-100))
        self.root.bind("<Shift-Down>", lambda event: self.navigate(100))
        self.root.bind("<Prior>", lambda event: self.navigate(-1000))
        self.root.bind("<Next>", lambda event: self.navigate(1000))

    # ------------------------------------------------------------------ #
    # Loading
    # ------------------------------------------------------------------ #

    def load_folder(self) -> None:
        if not self.confirm_discard_changes("Loading a new folder"):
            return
        folder = filedialog.askdirectory(title="Select Image Folder")
        if not folder:
            return
        try:
            scan = self.store.load_folder(folder)
        except OSError as exc:
            messagebox.showerror("Error", "Failed to read the folder:\n%s" % exc)
            return

        if not scan.count:
            messagebox.showwarning(
                "No Images",
                "No valid RGB images found in the folder or any of its subfolders",
            )
            return

        self.image_folder = folder
        self.scan_summary = self._format_scan_summary(scan)
        self.excel = None
        self.excel_names = {}
        self.source_path = None
        self.csv_headers = list(BASE_HEADERS)
        self.rebuild_filter_menu()
        self.update_table()
        self.load_current_image()
        self.update_info()

    @staticmethod
    def _format_scan_summary(scan: FolderScanResult) -> str:
        """Post-load summary of the recursive scan, shown in the info bar."""
        parts: List[str] = []
        if scan.folder_count > 1:
            parts.append("%d image folders" % scan.folder_count)
        if scan.duplicate_count:
            parts.append("%d duplicate(s) skipped" % scan.duplicate_count)
        return ", ".join(parts)

    def open_excel(self) -> None:
        if not self.store.records:
            messagebox.showwarning("No Data", "Please load an image folder first")
            return
        if not self.confirm_discard_changes("Loading another data file"):
            return

        path = filedialog.askopenfilename(
            title="Open Excel data file",
            filetypes=[("Excel files", "*.xlsx"), ("All files", "*.*")],
        )
        if not path:
            return

        try:
            source = ExcelSource.load(path)
        except ExcelError as exc:
            messagebox.showerror("Excel", str(exc))
            return
        except Exception as exc:  # pragma: no cover - defensive
            messagebox.showerror("Excel", "Failed to load the workbook:\n%s" % exc)
            return

        names = source.names()
        if not names:
            messagebox.showerror("Excel", "The selected sheet contains no data rows.")
            return

        prefixes = self.store.name_counts()
        suggestions = source.suggest_mapping([prefix for prefix, _ in prefixes])
        dialog = NameMappingDialog(self.root, prefixes, names, suggestions)
        self.root.wait_window(dialog)
        mapping = dialog.result
        if mapping is None:
            return

        chosen = {
            prefix: name for prefix, name in mapping.items() if name is not None
        }
        if not chosen:
            messagebox.showwarning(
                "Excel",
                "Every sample was set to %s, so there is nothing to join." % SKIP_CHOICE,
            )
            return

        # One (row, node) index per Excel Name, shared by prefixes that were
        # mapped to the same Name.
        indexes_by_name = {
            name: source.index_for_name(name) for name in set(chosen.values())
        }
        indexes_by_prefix = {
            prefix: indexes_by_name[name] for prefix, name in chosen.items()
        }
        stats = self.store.apply_excel_rows(indexes_by_prefix)

        self.excel = source
        self.excel_names = dict(mapping)
        self.source_path = path

        self.rebuild_filter_menu()
        self.store.ensure_current_visible()
        self.update_table()
        self.load_current_image()
        self.update_info()

        total_matched = sum(matched for matched, _ in stats.values())
        unused = sum(len(index) for index in indexes_by_name.values()) - total_matched
        lines = ["Sheet: %s" % source.sheet_name, ""]
        for prefix, count in prefixes:
            matched, unmatched = stats.get(prefix, (0, count))
            lines.append(
                "%s -> %s\n    %d matched, %d without data"
                % (prefix, mapping.get(prefix) or SKIP_CHOICE, matched, unmatched)
            )
        lines.append("")
        lines.append(
            "Total: %d matched, %d without data\nExcel rows without an image: %d"
            % (total_matched, len(self.store) - total_matched, max(0, unused))
        )
        messagebox.showinfo("Excel loaded", "\n".join(lines))

    def save_excel(self) -> None:
        if self.excel is None:
            messagebox.showwarning("No Excel", "No Excel data file is loaded.")
            return
        dirty = self.store.dirty_records()
        if not dirty:
            messagebox.showinfo("Save to Excel", "There are no unsaved changes.")
            return

        try:
            written, backup_created, skipped = self.excel.write_records(dirty)
        except ExcelFileLockedError as exc:
            messagebox.showerror("File locked", str(exc))
            return
        except ExcelError as exc:
            messagebox.showerror("Save failed", str(exc))
            return
        except Exception as exc:  # pragma: no cover - defensive
            messagebox.showerror("Save failed", "Failed to save the workbook:\n%s" % exc)
            return

        self.store.clear_dirty([record for record in dirty if record.can_write_back])
        self.update_table()
        self.update_info()

        message = "Updated %d Status cell(s) in %s." % (
            written,
            os.path.basename(self.excel.path),
        )
        if backup_created:
            message += "\nBackup created: %s" % os.path.basename(self.excel.backup_path)
        if skipped:
            message += (
                "\n%d changed row(s) had no Excel source row and were not written."
                % skipped
            )
        messagebox.showinfo("Saved", message)

    def load_csv(self) -> None:
        if not self.store.records:
            messagebox.showwarning("No Data", "Please load a folder first")
            return
        if not self.confirm_discard_changes("Loading another data file"):
            return

        path = filedialog.askopenfilename(
            title="Load Label CSV",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
        )
        if not path:
            return

        try:
            data = load_label_csv(path, self.label_set)
        except Exception as exc:
            messagebox.showerror("Error", "Failed to load CSV: %s" % exc)
            return

        self.csv_headers = data.headers
        matched = self.store.apply_csv_labels(data.labels, data.extras)
        self.excel = None
        self.excel_names = {}
        self.source_path = path

        self.rebuild_filter_menu()
        self.store.ensure_current_visible()
        self.update_table()
        self.load_current_image()
        self.update_info()
        messagebox.showinfo(
            "Success", "Loaded %d labels from %s" % (matched, os.path.basename(path))
        )

    def save_csv(self) -> bool:
        if not self.store.records:
            messagebox.showwarning("No Data", "No data to save")
            return False

        path = filedialog.asksaveasfilename(
            title="Save Label CSV",
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
        )
        if not path:
            return False

        try:
            count = save_label_csv(path, self.store.records, self.csv_headers)
        except Exception as exc:
            messagebox.showerror("Error", "Failed to save CSV: %s" % exc)
            return False

        self.store.clear_dirty()
        self.update_table()
        self.update_info()
        messagebox.showinfo(
            "Success", "Saved %d labels to %s" % (count, os.path.basename(path))
        )
        return True

    # ------------------------------------------------------------------ #
    # Filtering
    # ------------------------------------------------------------------ #

    def rebuild_filter_menu(self) -> None:
        """Recreate the checkbox menu from the status values currently present."""
        statuses = self.store.unique_statuses()
        previous = {key: var.get() for key, var in self._filter_vars.items()}

        self._filter_vars = {}
        self._filter_lookup = {}
        self.filter_menu.delete(0, tk.END)

        for status in statuses:
            key = status_display(status)
            variable = tk.BooleanVar(value=previous.get(key, True))
            self._filter_vars[key] = variable
            self._filter_lookup[key] = status
            self.filter_menu.add_checkbutton(
                label=key, variable=variable, command=self.on_filter_changed
            )

        if statuses:
            self.filter_menu.add_separator()
        self.filter_menu.add_command(label="All", command=lambda: self.set_all_filters(True))
        self.filter_menu.add_command(label="None", command=lambda: self.set_all_filters(False))

        self.apply_filter(update_view=False)

    def set_all_filters(self, value: bool) -> None:
        for variable in self._filter_vars.values():
            variable.set(value)
        self.on_filter_changed()

    def selected_filter_values(self) -> List[Optional[str]]:
        return [
            self._filter_lookup[key]
            for key, variable in self._filter_vars.items()
            if variable.get()
        ]

    def apply_filter(self, update_view: bool = True) -> None:
        values = self.selected_filter_values()
        if len(values) == len(self._filter_vars):
            self.store.set_filter(None)
        else:
            self.store.set_filter(values)
        self.store.ensure_current_visible()
        if update_view:
            self.update_table()
            self.load_current_image()
            self.update_info()

    def on_filter_changed(self) -> None:
        self.apply_filter(update_view=True)
        self.update_filter_button()

    def update_filter_button(self) -> None:
        if self.store.filter_active:
            self.filter_button.config(text="Filter: %d/%d" % (
                self.store.visible_count,
                len(self.store),
            ))
        else:
            self.filter_button.config(text="Status filter")

    # ------------------------------------------------------------------ #
    # Table
    # ------------------------------------------------------------------ #

    def _row_values(self, record: ImageRecord) -> Tuple[str, ...]:
        return (
            "*" if record.dirty else "",
            record.name,
            str(record.row),
            str(record.node),
            format_metric(record.metric("ON")),
            format_metric(record.metric("OFF")),
            format_metric(record.metric("ON/OFF")),
            format_metric(record.metric("gm")),
            format_metric(record.metric("Vth")),
            format_metric(record.metric("Carrier Mobility")),
            record.status_text,
        )

    def _status_tag(self, status: Optional[str]) -> str:
        tag = self._status_tags.get(status)
        if tag is None:
            tag = "status_%d" % len(self._status_tags)
            self._status_tags[status] = tag
            self.tree.tag_configure(tag, background=self.label_set.color_for(status))
        return tag

    def _row_tags(self, record: ImageRecord) -> Tuple[str, ...]:
        tags = [self._status_tag(record.status)]
        if record.dirty:
            tags.append("dirty")
        return tuple(tags)

    def update_table(self) -> None:
        """Rebuild the whole table from the filtered record list."""
        self._suspend_tree_event = True
        try:
            children = self.tree.get_children()
            if children:
                self.tree.delete(*children)
            self._iid_to_record = {}
            self._record_to_iid = {}

            for index, record in enumerate(self.store.visible()):
                iid = "R%d" % index
                self.tree.insert(
                    "",
                    "end",
                    iid=iid,
                    values=self._row_values(record),
                    tags=self._row_tags(record),
                )
                self._iid_to_record[iid] = record
                self._record_to_iid[id(record)] = iid
        finally:
            self._suspend_tree_event = False

        self.restore_selection()

    def refresh_record_row(self, record: ImageRecord) -> None:
        """Update a single already displayed row (fast path after an edit)."""
        iid = self._record_to_iid.get(id(record))
        if iid is None or not self.tree.exists(iid):
            return
        self.tree.item(iid, values=self._row_values(record), tags=self._row_tags(record))

    def restore_selection(self) -> None:
        """Reselect the previously selected records that are still visible."""
        visible = set(id(record) for record in self.store.visible())
        wanted = [
            record for record in self._selected_records if id(record) in visible
        ]
        current = self.store.current_record
        if current is not None and id(current) in visible and current not in wanted:
            wanted.append(current)

        iids = [
            self._record_to_iid[id(record)]
            for record in wanted
            if id(record) in self._record_to_iid
        ]
        self._suspend_tree_event = True
        try:
            if iids:
                self.tree.selection_set(iids)
            else:
                self.tree.selection_remove(self.tree.selection())
        finally:
            self._suspend_tree_event = False

        self._selected_records = wanted
        focus_record = current if current is not None else (wanted[0] if wanted else None)
        if focus_record is not None:
            iid = self._record_to_iid.get(id(focus_record))
            if iid is not None and self.tree.exists(iid):
                self.tree.focus(iid)
                self.tree.see(iid)

    def select_current(self) -> None:
        """Make the current record the one and only selection."""
        record = self.store.current_record
        if record is None:
            return
        iid = self._record_to_iid.get(id(record))
        if iid is None or not self.tree.exists(iid):
            return
        self._suspend_tree_event = True
        try:
            self.tree.selection_set(iid)
            self.tree.focus(iid)
            self.tree.see(iid)
        finally:
            self._suspend_tree_event = False
        self._selected_records = [record]

    def on_tree_select(self, event: "tk.Event") -> None:
        if self._suspend_tree_event:
            return
        selection = self.tree.selection()
        records = [
            self._iid_to_record[iid] for iid in selection if iid in self._iid_to_record
        ]
        self._selected_records = records
        if not records:
            return
        if records[0] is not self.store.current_record:
            self.store.current_record = records[0]
            self.load_current_image()
            self.update_info()

    def selected_records(self) -> List[ImageRecord]:
        if self._selected_records:
            return list(self._selected_records)
        current = self.store.current_record
        return [current] if current is not None else []

    def sort_column(self, column: str) -> None:
        if not self.store.records:
            return
        current = self.store.current_record
        self.store.sort_by(column)
        # The current record is tracked by identity, so it survives the sort.
        self.store.current_record = current
        self.store.ensure_current_visible()
        self.update_table()
        self.update_info()

    # ------------------------------------------------------------------ #
    # Image display
    # ------------------------------------------------------------------ #

    def load_current_image(self) -> None:
        record = self.store.current_record
        if record is None or not record.path:
            self._rgb_image = None
            self.rgb_canvas.delete("all")
            return
        try:
            self._rgb_image = Image.open(record.path)
            self.display_image()
        except Exception as exc:
            self._rgb_image = None
            self.rgb_canvas.delete("all")
            self.rgb_canvas.create_text(
                10, 10, anchor="nw", fill="white", text="Failed to load image: %s" % exc
            )

    def display_image(self) -> None:
        if self._rgb_image is None:
            return
        try:
            if not self.rgb_canvas.winfo_exists():
                return
            width = self.rgb_canvas.winfo_width()
            height = self.rgb_canvas.winfo_height()
            if width <= 1 or height <= 1:
                # Canvas not laid out yet - retry once it is.
                self.root.after(100, self.display_image)
                return
            resized = self.resize_image_to_fit(self._rgb_image, width, height)
            self._rgb_photo = ImageTk.PhotoImage(resized)
            self.rgb_canvas.delete("all")
            self.rgb_canvas.create_image(
                width // 2, height // 2, image=self._rgb_photo, anchor="center"
            )
        except tk.TclError:
            # Widget destroyed while a redraw was pending (e.g. on close).
            return

    @staticmethod
    def resize_image_to_fit(
        image: Image.Image, max_width: int, max_height: int
    ) -> Image.Image:
        """Scale ``image`` into the box, preserving the aspect ratio."""
        image_width, image_height = image.size
        if image_width <= 0 or image_height <= 0:
            return image
        scale = min(max_width / image_width, max_height / image_height) * 0.95
        new_width = max(1, int(image_width * scale))
        new_height = max(1, int(image_height * scale))
        return image.resize((new_width, new_height), Image.LANCZOS)

    def on_canvas_resize(self, event: "tk.Event") -> None:
        """Redraw the current image when the canvas itself changes size.

        Fires for window resizes and for sash drags (which resize the image
        pane, and therefore the canvas packed into it). Debounced with a
        short ``after`` so dragging the sash stays smooth instead of
        re-decoding the image on every intermediate pixel.
        """
        if self._canvas_resize_job is not None:
            try:
                self.root.after_cancel(self._canvas_resize_job)
            except Exception:  # pragma: no cover - defensive
                pass
        self._canvas_resize_job = self.root.after(30, self._do_canvas_resize)

    def _do_canvas_resize(self) -> None:
        self._canvas_resize_job = None
        if self._rgb_image is not None:
            self.display_image()

    def flash_status(self, value: Optional[str]) -> None:
        """Flash the applied status over the image for one second.

        Drawn directly on ``rgb_canvas`` (tagged ``"status_flash"``) rather
        than a separately placed ``Label`` widget, so there is nothing left
        mapped over the canvas between flashes - a permanently `place()`d
        overlay label rendered as a persistent dark bar even with empty text.
        """
        if self._overlay_job is not None:
            try:
                self.root.after_cancel(self._overlay_job)
            except Exception:  # pragma: no cover - defensive
                pass
            self._overlay_job = None

        text = value if value else BLANK_DISPLAY
        color = self.label_set.overlay_color_for(value)
        try:
            if not self.rgb_canvas.winfo_exists():
                return
            self.rgb_canvas.delete("status_flash")
            width = self.rgb_canvas.winfo_width()
            height = self.rgb_canvas.winfo_height()
            self.rgb_canvas.create_text(
                width // 2,
                height // 2,
                text=text,
                font=("Arial", 72, "bold"),
                fill=color,
                tags="status_flash",
            )
        except tk.TclError:  # pragma: no cover - defensive
            return
        self._overlay_job = self.root.after(1000, self._clear_overlay)

    def _clear_overlay(self) -> None:
        self._overlay_job = None
        try:
            if self.rgb_canvas.winfo_exists():
                self.rgb_canvas.delete("status_flash")
        except tk.TclError:  # pragma: no cover - defensive
            pass

    # ------------------------------------------------------------------ #
    # Editing / navigation
    # ------------------------------------------------------------------ #

    def _on_key_press(self, event: "tk.Event") -> Optional[str]:
        """Dispatch label / clear hotkeys of the active set."""
        if event.state & 0x4:  # Control held - leave Ctrl+O/S/L and friends alone
            return None
        keysym = event.keysym
        if keysym in CLEAR_KEYS:
            self.set_status(None)
            return "break"
        label = self.label_set.by_key(keysym, self.config.digit_ordinals)
        if label is None:
            return None
        self.set_status(label.name)
        return "break"

    def set_status(self, value: Optional[str]) -> None:
        """Apply ``value`` to every selected row (any status may be changed).

        ``value`` is written in the active label set's spelling when it names
        one of its labels; other strings are applied verbatim.
        """
        targets = self.selected_records()
        if not targets:
            return

        value = self.label_set.canonical(value)
        changed = self.store.apply_status(targets, value)
        if not changed:
            if self.config.auto_advance and len(targets) == 1:
                self.navigate(1)
            return

        self._after_status_change(changed)
        self.flash_status(value)
        if self.config.auto_advance and len(targets) == 1:
            self.navigate(1)

    def revert_status(self) -> None:
        """Restore every selected row to the label held by the source file.

        This is the counterpart of :meth:`set_status`: instead of assigning a
        fixed value it puts each record back to its ``original_status`` (blank
        for rows that were never in the data file), which also makes the record
        clean again.
        """
        targets = self.selected_records()
        if not targets:
            return

        changed = self.store.revert_status(targets)
        if not changed:
            return

        self._after_status_change(changed)

        # After the revert every target sits on its original value; flash it
        # when they agree, otherwise just say what happened.
        restored = {record.status for record in targets}
        self.flash_status(restored.pop() if len(restored) == 1 else "Reverted")

    def _after_status_change(self, changed: Sequence[ImageRecord]) -> None:
        """Refresh the UI after ``changed`` records got a new status."""
        # The dropdown always mirrors the status values actually present, so it
        # is rebuilt whenever a value appears or disappears.
        present = {status_display(status) for status in self.store.unique_statuses()}
        needs_menu_rebuild = present != set(self._filter_vars)
        if needs_menu_rebuild:
            self.rebuild_filter_menu()

        # Re-apply the filter right away; rows that no longer match disappear.
        hidden = [record for record in changed if not self.store.matches_filter(record)]
        if hidden or needs_menu_rebuild:
            self.store.ensure_current_visible()
            self.update_table()
            self.load_current_image()
        else:
            for record in changed:
                self.refresh_record_row(record)

        self.update_info()

    def navigate(self, delta: int) -> None:
        if not self.store.visible():
            return
        before = self.store.current_record
        record = self.store.navigate(delta)
        if record is None or record is before:
            return
        self.select_current()
        self.load_current_image()
        self.update_info()

    # ------------------------------------------------------------------ #
    # Info bar / title
    # ------------------------------------------------------------------ #

    @property
    def excel_name_summary(self) -> Optional[str]:
        """Excel ``Name`` (single sample) or ``'N samples'`` for the info bar."""
        used = [name for name in self.excel_names.values() if name]
        if not used:
            return None
        if len(used) == 1:
            return used[0]
        return "%d samples" % len(used)

    def update_info(self) -> None:
        total = len(self.store)
        dirty_count = self.store.dirty_count

        if not total:
            self.info_label.config(text="No folder loaded")
            self.root.title(APP_TITLE)
            self.save_excel_button.config(state=tk.DISABLED)
            self.update_filter_button()
            return

        visible = self.store.visible()
        position = self.store.current_index
        parts = [
            "Image %d/%d" % (position + 1 if position >= 0 else 0, len(visible)),
        ]

        full_counts = self.store.status_counts()
        visible_counts = self.store.status_counts(visible)
        filtering = self.store.filter_active
        count_parts = []
        for status in self.store.unique_statuses():
            label = status_display(status)
            if filtering:
                count_parts.append(
                    "%s: %d/%d"
                    % (label, visible_counts.get(status, 0), full_counts.get(status, 0))
                )
            else:
                count_parts.append("%s: %d" % (label, full_counts.get(status, 0)))
        if count_parts:
            parts.append(" | ".join(count_parts))

        if filtering:
            parts.append(
                "Filter: %s — %d/%d"
                % (self.store.filter_description(), len(visible), total)
            )

        if self.image_folder:
            folder_text = os.path.basename(self.image_folder)
            if self.scan_summary:
                folder_text += " (%s)" % self.scan_summary
            parts.append("Folder: %s" % folder_text)
        if self.source_path:
            source = os.path.basename(self.source_path)
            summary = self.excel_name_summary
            if summary:
                source += " [%s]" % summary
            parts.append("Source: %s" % source)
        parts.append("Unsaved: %d" % dirty_count)

        self.info_label.config(text=" | ".join(parts))

        title = APP_TITLE
        if self.image_folder:
            title += " - %s" % os.path.basename(self.image_folder)
        if dirty_count:
            title = "*" + title + " (%d unsaved)" % dirty_count
        self.root.title(title)

        self.save_excel_button.config(
            state=tk.NORMAL if (self.excel is not None and dirty_count) else tk.DISABLED
        )
        self.update_filter_button()

    # ------------------------------------------------------------------ #
    # Closing
    # ------------------------------------------------------------------ #

    def save_current_source(self) -> bool:
        """Save through whichever source is loaded; ``True`` when saved."""
        if self.excel is not None:
            dirty = self.store.dirty_records()
            if not dirty:
                return True
            try:
                self.excel.write_records(dirty)
            except ExcelFileLockedError as exc:
                messagebox.showerror("File locked", str(exc))
                return False
            except ExcelError as exc:
                messagebox.showerror("Save failed", str(exc))
                return False
            self.store.clear_dirty(
                [record for record in dirty if record.can_write_back]
            )
            self.update_info()
            return True
        return self.save_csv()

    def confirm_discard_changes(self, action: str) -> bool:
        """Ask before throwing unsaved changes away; ``True`` to continue."""
        if not self.store.dirty_count:
            return True
        answer = messagebox.askyesnocancel(
            "Unsaved changes",
            "%s will discard %d unsaved change(s).\n\n"
            "Yes = save first, No = discard, Cancel = stay here."
            % (action, self.store.dirty_count),
        )
        if answer is None:
            return False
        if answer:
            return self.save_current_source()
        return True

    def on_close(self) -> None:
        if self.store.dirty_count:
            answer = messagebox.askyesnocancel(
                "Unsaved changes",
                "There are %d unsaved change(s).\n\n"
                "Yes = save and close, No = close without saving, Cancel = stay."
                % self.store.dirty_count,
            )
            if answer is None:
                return
            if answer and not self.save_current_source():
                return
        self.root.destroy()


def _icon_path() -> Optional[str]:
    """``assets/icon.ico`` next to the sources, or inside the PyInstaller bundle."""
    candidates = []
    bundle = getattr(sys, "_MEIPASS", None)
    if bundle:
        candidates.append(os.path.join(bundle, "assets", "icon.ico"))
    here = os.path.dirname(os.path.abspath(__file__))
    candidates.append(os.path.join(os.path.dirname(here), "assets", "icon.ico"))
    for candidate in candidates:
        if os.path.isfile(candidate):
            return candidate
    return None


def main() -> None:
    """Start the ImageMarker application."""
    root = tk.Tk()
    icon = _icon_path()
    if icon:
        try:
            root.iconbitmap(default=icon)
        except tk.TclError:  # not on Windows, or a broken .ico - keep the default
            pass
    ImageMarkerApp(root)
    root.mainloop()


if __name__ == "__main__":  # pragma: no cover
    main()
