"""Tkinter dialogs for editing a label set and capturing a hotkey."""

from __future__ import annotations

import tkinter as tk
from tkinter import colorchooser, messagebox, ttk
from typing import List, Optional

from .label_sets import (
    MAX_LABELS,
    RESERVED_KEYS,
    LabelDef,
    LabelSet,
    is_dark,
    key_display,
    normalize_key,
    parse_hex,
)

#: Keys that are only modifiers - the capture dialog ignores them.
_MODIFIER_KEYSYMS = {
    "Shift_L", "Shift_R", "Control_L", "Control_R", "Alt_L", "Alt_R",
    "Meta_L", "Meta_R", "Super_L", "Super_R", "Caps_Lock", "Num_Lock",
    "Win_L", "Win_R", "Hyper_L", "Hyper_R", "ISO_Level3_Shift",
}

#: A rotating palette for freshly added labels.
_PALETTE = (
    "#2e9e4f", "#d64545", "#e8a33d", "#3b82f6", "#8b5cf6",
    "#0ea5a4", "#db2777", "#6b7280", "#84cc16",
)


class KeyCaptureDialog(tk.Toplevel):
    """Modal "press a key" prompt; ``result`` is the keysym or ``None``."""

    def __init__(self, parent: tk.Misc) -> None:
        super().__init__(parent)
        self.title("Press a key")
        self.resizable(False, False)
        self.result: Optional[str] = None
        tk.Label(
            self,
            text="Press the key to bind to this label.\n"
            "Letters, digits, F1-F12 and keys like → or Insert are fine.\n"
            "Esc cancels.",
            justify=tk.CENTER,
            padx=24,
            pady=18,
        ).pack()
        self.bind("<KeyPress>", self._on_key)
        self.protocol("WM_DELETE_WINDOW", self._cancel)
        self.transient(parent)
        self.update_idletasks()
        self.grab_set()
        self.focus_force()

    def _on_key(self, event: "tk.Event") -> str:
        keysym = event.keysym
        if keysym in _MODIFIER_KEYSYMS:
            return "break"
        if keysym == "Escape":
            self._cancel()
            return "break"
        self.result = normalize_key(keysym)
        self.destroy()
        return "break"

    def _cancel(self) -> None:
        self.result = None
        self.destroy()


class LabelSetDialog(tk.Toplevel):
    """Edit a copy of a label set; ``result`` is the new set or ``None``."""

    def __init__(self, parent: tk.Misc, label_set: LabelSet) -> None:
        super().__init__(parent)
        self.title("Edit label set")
        self.minsize(640, 420)
        self.result: Optional[LabelSet] = None
        self._labels: List[LabelDef] = label_set.copy().labels
        self._selected: Optional[int] = None
        self._loading = False

        outer = tk.Frame(self, padx=10, pady=10)
        outer.pack(fill=tk.BOTH, expand=True)

        # Set name ------------------------------------------------------------
        head = tk.Frame(outer)
        head.pack(fill=tk.X, pady=(0, 8))
        tk.Label(head, text="Set name:").pack(side=tk.LEFT)
        self.name_var = tk.StringVar(value=label_set.name)
        tk.Entry(head, textvariable=self.name_var, width=40).pack(
            side=tk.LEFT, padx=(6, 0), fill=tk.X, expand=True
        )

        body = tk.Frame(outer)
        body.pack(fill=tk.BOTH, expand=True)
        body.grid_columnconfigure(0, weight=3)
        body.grid_columnconfigure(1, weight=2)
        body.grid_rowconfigure(0, weight=1)

        # Label list ------------------------------------------------------------
        list_frame = tk.LabelFrame(body, text="Labels (in order - digits 1..9 follow this order)")
        list_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        self.tree = ttk.Treeview(
            list_frame, columns=("name", "keys", "color"), show="headings", height=9,
            selectmode="browse",
        )
        self.tree.heading("name", text="Label (Status text)")
        self.tree.heading("keys", text="Keys")
        self.tree.heading("color", text="Colour")
        self.tree.column("name", width=180, anchor="w")
        self.tree.column("keys", width=110, anchor="center")
        self.tree.column("color", width=80, anchor="center")
        self.tree.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=6, pady=6)
        self.tree.bind("<<TreeviewSelect>>", self._on_select)

        list_buttons = tk.Frame(list_frame)
        list_buttons.pack(side=tk.TOP, fill=tk.X, padx=6, pady=(0, 6))
        tk.Button(list_buttons, text="Add", width=7, command=self._add_label).pack(side=tk.LEFT)
        tk.Button(list_buttons, text="Remove", width=7, command=self._remove_label).pack(
            side=tk.LEFT, padx=(4, 0)
        )
        tk.Button(list_buttons, text="Up", width=5, command=lambda: self._move(-1)).pack(
            side=tk.LEFT, padx=(12, 0)
        )
        tk.Button(list_buttons, text="Down", width=5, command=lambda: self._move(1)).pack(
            side=tk.LEFT, padx=(4, 0)
        )

        # Editor for the selected label ------------------------------------------
        edit = tk.LabelFrame(body, text="Selected label")
        edit.grid(row=0, column=1, sticky="nsew")
        edit.grid_columnconfigure(1, weight=1)

        tk.Label(edit, text="Name:").grid(row=0, column=0, sticky="w", padx=6, pady=(8, 2))
        self.label_name_var = tk.StringVar()
        self.label_name_var.trace_add("write", lambda *_: self._on_name_edited())
        self.name_entry = tk.Entry(edit, textvariable=self.label_name_var)
        self.name_entry.grid(row=0, column=1, sticky="ew", padx=(0, 6), pady=(8, 2))

        tk.Label(edit, text="Colour:").grid(row=1, column=0, sticky="w", padx=6, pady=2)
        color_row = tk.Frame(edit)
        color_row.grid(row=1, column=1, sticky="ew", padx=(0, 6), pady=2)
        self.color_swatch = tk.Label(color_row, text="  #000000  ", relief=tk.SUNKEN, width=12)
        self.color_swatch.pack(side=tk.LEFT)
        tk.Button(color_row, text="Choose...", command=self._choose_color).pack(
            side=tk.LEFT, padx=(6, 0)
        )

        tk.Label(edit, text="Keys:").grid(row=2, column=0, sticky="nw", padx=6, pady=2)
        keys_frame = tk.Frame(edit)
        keys_frame.grid(row=2, column=1, sticky="nsew", padx=(0, 6), pady=2)
        edit.grid_rowconfigure(2, weight=1)
        self.keys_list = tk.Listbox(keys_frame, height=4, exportselection=False)
        self.keys_list.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        key_buttons = tk.Frame(keys_frame)
        key_buttons.pack(side=tk.LEFT, fill=tk.Y, padx=(6, 0))
        tk.Button(key_buttons, text="Add key...", width=10, command=self._add_key).pack(fill=tk.X)
        tk.Button(key_buttons, text="Remove key", width=10, command=self._remove_key).pack(
            fill=tk.X, pady=(4, 0)
        )

        tk.Label(edit, text="Description:").grid(row=3, column=0, sticky="w", padx=6, pady=2)
        self.desc_var = tk.StringVar()
        self.desc_var.trace_add("write", lambda *_: self._on_desc_edited())
        tk.Entry(edit, textvariable=self.desc_var).grid(
            row=3, column=1, sticky="ew", padx=(0, 6), pady=(2, 8)
        )

        tk.Label(
            edit,
            text="Reserved keys: " + ", ".join(key_display(k) for k in RESERVED_KEYS)
            + "\n(navigation, revert and clear).",
            justify=tk.LEFT,
            fg="gray30",
            font=("Arial", 8),
        ).grid(row=4, column=0, columnspan=2, sticky="w", padx=6, pady=(0, 6))

        # Buttons ----------------------------------------------------------------
        buttons = tk.Frame(outer)
        buttons.pack(fill=tk.X, pady=(10, 0))
        tk.Button(buttons, text="Cancel", width=10, command=self._on_cancel).pack(side=tk.RIGHT)
        tk.Button(buttons, text="OK", width=10, command=self._on_ok).pack(
            side=tk.RIGHT, padx=(0, 6)
        )

        self.bind("<Escape>", lambda event: self._on_cancel())
        self.protocol("WM_DELETE_WINDOW", self._on_cancel)

        self._refresh_tree(select=0 if self._labels else None)
        self.transient(parent)
        self.update_idletasks()
        self.grab_set()
        self.focus_force()

    # -- helpers ------------------------------------------------------------------

    def _refresh_tree(self, select: Optional[int] = None) -> None:
        self._loading = True
        try:
            self.tree.delete(*self.tree.get_children())
            for index, label in enumerate(self._labels):
                tag = "row%d" % index
                try:
                    parse_hex(label.color)
                    background = label.row_color
                except ValueError:
                    background = "white"
                self.tree.tag_configure(tag, background=background)
                self.tree.insert(
                    "", "end", iid=str(index),
                    values=(label.name, label.key_hint, label.color), tags=(tag,),
                )
            if select is not None and 0 <= select < len(self._labels):
                self.tree.selection_set(str(select))
                self.tree.focus(str(select))
                self._selected = select
            else:
                self._selected = None
        finally:
            self._loading = False
        self._load_editor()

    def _load_editor(self) -> None:
        self._loading = True
        try:
            label = self._current()
            enabled = tk.NORMAL if label is not None else tk.DISABLED
            self.name_entry.config(state=enabled)
            self.keys_list.delete(0, tk.END)
            if label is None:
                self.label_name_var.set("")
                self.desc_var.set("")
                self.color_swatch.config(text="", bg=self.cget("bg"))
                return
            self.label_name_var.set(label.name)
            self.desc_var.set(label.description)
            self._show_color(label.color)
            for key in label.keys:
                self.keys_list.insert(tk.END, "%s   (%s)" % (key_display(key), key))
        finally:
            self._loading = False

    def _show_color(self, color: str) -> None:
        try:
            parse_hex(color)
        except ValueError:
            self.color_swatch.config(text=color, bg="white", fg="red")
            return
        self.color_swatch.config(
            text="  %s  " % color, bg=color, fg="white" if is_dark(color) else "black"
        )

    def _current(self) -> Optional[LabelDef]:
        if self._selected is None or not 0 <= self._selected < len(self._labels):
            return None
        return self._labels[self._selected]

    def _update_row(self) -> None:
        label = self._current()
        if label is None or self._selected is None:
            return
        iid = str(self._selected)
        if self.tree.exists(iid):
            self.tree.item(iid, values=(label.name, label.key_hint, label.color))
            try:
                parse_hex(label.color)
                self.tree.tag_configure("row%d" % self._selected, background=label.row_color)
            except ValueError:
                pass

    # -- events ---------------------------------------------------------------------

    def _on_select(self, event: "tk.Event") -> None:
        if self._loading:
            return
        selection = self.tree.selection()
        self._selected = int(selection[0]) if selection else None
        self._load_editor()

    def _on_name_edited(self) -> None:
        if self._loading:
            return
        label = self._current()
        if label is None:
            return
        label.name = self.label_name_var.get().strip()
        self._update_row()

    def _on_desc_edited(self) -> None:
        if self._loading:
            return
        label = self._current()
        if label is not None:
            label.description = self.desc_var.get().strip()

    def _choose_color(self) -> None:
        label = self._current()
        if label is None:
            return
        try:
            initial = label.color if parse_hex(label.color) else "#808080"
        except ValueError:
            initial = "#808080"
        chosen = colorchooser.askcolor(color=initial, parent=self, title="Label colour")
        if not chosen or not chosen[1]:
            return
        label.color = str(chosen[1]).lower()
        self._show_color(label.color)
        self._update_row()

    def _add_key(self) -> None:
        label = self._current()
        if label is None:
            return
        dialog = KeyCaptureDialog(self)
        self.wait_window(dialog)
        key = dialog.result
        if not key:
            return
        if key in RESERVED_KEYS:
            messagebox.showwarning(
                "Reserved key",
                "'%s' is reserved for navigation, revert or clear." % key_display(key),
                parent=self,
            )
            return
        for other in self._labels:
            if other is not label and key in other.keys:
                messagebox.showwarning(
                    "Key in use",
                    "'%s' is already bound to '%s'." % (key_display(key), other.name),
                    parent=self,
                )
                return
        if key not in label.keys:
            label.keys.append(key)
        self._load_editor()
        self._update_row()

    def _remove_key(self) -> None:
        label = self._current()
        if label is None:
            return
        selection = self.keys_list.curselection()
        if not selection:
            return
        del label.keys[selection[0]]
        self._load_editor()
        self._update_row()

    def _add_label(self) -> None:
        if len(self._labels) >= MAX_LABELS:
            messagebox.showwarning(
                "Too many labels", "A label set can hold at most %d labels." % MAX_LABELS,
                parent=self,
            )
            return
        color = _PALETTE[len(self._labels) % len(_PALETTE)]
        self._labels.append(LabelDef("NEW_LABEL", color))
        self._refresh_tree(select=len(self._labels) - 1)
        self.name_entry.focus_set()
        self.name_entry.select_range(0, tk.END)

    def _remove_label(self) -> None:
        if self._selected is None:
            return
        index = self._selected
        del self._labels[index]
        self._refresh_tree(select=min(index, len(self._labels) - 1) if self._labels else None)

    def _move(self, delta: int) -> None:
        if self._selected is None:
            return
        index = self._selected
        target = index + delta
        if not 0 <= target < len(self._labels):
            return
        self._labels[index], self._labels[target] = self._labels[target], self._labels[index]
        self._refresh_tree(select=target)

    def _on_ok(self) -> None:
        candidate = LabelSet(self.name_var.get().strip(), self._labels)
        problems = candidate.validate()
        if problems:
            messagebox.showerror("Label set", "\n".join(problems), parent=self)
            return
        self.result = candidate
        self.destroy()

    def _on_cancel(self) -> None:
        self.result = None
        self.destroy()


__all__ = ["KeyCaptureDialog", "LabelSetDialog"]
