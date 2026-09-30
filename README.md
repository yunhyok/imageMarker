# ImageMarker 2.0.0

A Windows desktop tool for **human review and labeling of per-device RGB slice images**. It shows images beside electrical measurements, lets a reviewer assign a label, and saves the result to an Excel workbook or CSV. It does not detect defects, calculate measurements, crop images, or train a model.

Documentation: [한국어 상세 안내](README.ko.md) · [한국어 HTML](README.ko.companion.html) · [English HTML](README.companion.html) · [Implementation specification](docs/SPEC.md).

## Start here

If you have the packaged application, run `ImageMarker.exe`; the source installation below is unnecessary. The interface uses English menu and button names.

1. Click **Load Folder** and choose a folder containing files named `<name>_rgb_<row>_<node>.png`, for example `SAM 1_rgb_01_07.png`. All subfolders are scanned.
2. Choose a label set from **Labels**. The initial set is **GOOD / BAD / OPEN**. Select the set before loading CSV, because CSV label normalization uses the active set.
3. For Excel, click **Open Excel...**, choose an `.xlsx` file, and confirm each sample-to-`Name` pairing. For CSV, click **Load CSV** instead.
4. Select a table row, inspect its image and measurements, and use a label button or shortcut.
5. Click **Save to Excel** for workbook changes, or **Save CSV** for a CSV export. Changes remain in memory until saved.

The upper image pane preserves the image's aspect ratio. Drag the divider to give the image or table more space. The table shows an unsaved `*` column, Name, Row, Node, ON, OFF, ON/OFF, gm, Vth, Carrier Mobility, and Status.

![ImageMarker 2.0 main window with synthetic sample data](assets/screenshot.png)

## Image folders and selection

Only PNG filenames matching the pattern are included, case-insensitively; other files, including manifests, are ignored. Row and Node are parsed as integers, so `01` and `1` refer to the same coordinate. There is no fixed requirement for 26 rows, 38 nodes, or a particular number of images.

The scan sorts directory and file names, keeps the first occurrence of each `(name, row, node)`, and reports skipped duplicate counts. Initial order is Name, Row, Node. A sample is the filename prefix before `_rgb_`, not its containing folder's name.

Click a row to view its image. Use Ctrl+click for separate rows and Shift+click for a range. Label, Clear, and Revert actions affect every selected row. Keyboard navigation selects one current row. Click a column heading to sort; clicking it again reverses the order, while the current image remains associated with its record.

If an image cannot be decoded, the canvas displays an error; its table record remains present.

## Excel workflow

**Load images first.** The app reads the workbook's first worksheet; there is no sheet picker in the interface. Row 1 must contain `Name`, `Row`, `Node`, and `Status`. Header matching ignores case and surrounding spaces, and columns may be reordered. ON, OFF, ON/OFF, gm, Vth, and Carrier Mobility are optional.

Rows with unusable Row or Node values are ignored. Integer numbers and text such as `01` or `1.0` work. Missing or nonnumeric measurements display blank; formulas are read through their cached values, and ImageMarker does not recalculate them.

The matching dialog shows one row per loaded filename prefix:

- It suggests a pairing only when both names contain the same sample number, such as `SAM 1`, `sam1`, or `sam_1`, and exactly one Excel Name has that number. Missing or ambiguous numbers leave the choice at **(skip)**.
- Review every suggestion and choose the appropriate Excel Name manually where needed.
- After confirmation, images join by integer `(Row, Node)` within that Name. Duplicate coordinates within one Excel Name use its first worksheet row.
- **(skip)** and unmatched images remain available for review with blank Status and measurements. The load summary reports matched and unmatched counts. There is no separate visible “no data” badge on the table.
- Choosing **(skip)** for every sample or canceling the dialog does not attach the new workbook.

**Save to Excel** and **Ctrl+S** write the changed Status cells of all matched images, including rows hidden by a filter, to the original workbook. Other columns are not assigned by the application. The workbook is reopened and saved through openpyxl; this is not a byte-preserving file patch.

Before the first write, `data.xlsx` is copied to `data.backup.xlsx` beside it. An existing backup is reused and never refreshed; it is not a copy of the most recent save. A save with no writable updates creates no backup.

Successfully written rows become clean, and Revert restores their newly saved value. Changed rows without Excel coordinates are skipped and remain unsaved; the regular save dialog reports their count. Close the workbook in Excel and retry if ImageMarker reports a lock or permission error. Keep the worksheet's row/column layout unchanged while it is attached: write-back uses the cell positions remembered during loading.

**Before closing or loading another source, handle unmatched edits explicitly.** In 2.0.0, answering Yes to “save first” or “save and close” can continue even when Excel skipped these rows. Export them to CSV before leaving, or revert edits you do not need.

## CSV workflow and save scope

CSV is joined by the exact filename prefix plus integer Row and Node: `(name, row, node)`. Unlike Excel, there is no sample mapping dialog.

The loader reads UTF-8 with or without a BOM. Headers ignore surrounding spaces and case; the label column may be called `label`, `marker`, or `status` (in that priority). Output uses `name,row,node,label` plus the loaded extra headers, and is UTF-8 with BOM. Unknown headers are retained for matched images.

Values naming a label in the active set use that set's spelling (`good` → `GOOD`). Legacy aliases such as `ok` or `1` → `Pass`, and `-1` → `Open`, apply only when the target exists in the active set. Empty cells and `NONE`, `N/A`, `NA`, `AMBIGUOUS`, `UNKNOWN`, or `UNCLASSIFIED` become blank. Other values are preserved. CSV numbers are legacy aliases, not the active set's ordinal shortcuts.

**Save CSV** always asks for a destination and exports **all currently loaded image records**, including filtered-out rows and unchanged rows. It does not export CSV-only rows without loaded images or automatically add Excel measurement columns. Extra CSV fields are preserved only for records that carry them. Duplicate CSV keys use the last input row. Loading a CSV updates matching images only; unmatched images retain their previous status and data, so start with a fresh folder load when replacing a dataset completely.

A successful CSV export clears all unsaved markers and updates the Revert baseline. It does **not** attach the exported path as a new source, and it does **not** update Excel. When Excel remains attached, save to Excel **before** exporting CSV if both outputs are required: exporting first makes those labels clean, so a subsequent Excel save has no changes to write. Ctrl+S always means Excel save; use Save CSV in a CSV-only session.

## Label sets and shortcuts

| Preset | Labels and explicit keys | Ordinal keys when enabled |
|---|---|---|
| GOOD / BAD / OPEN (initial default) | GOOD: G; BAD: B; OPEN: O | 1, 2, 3 |
| PASS / FAIL | PASS: P; FAIL: F | 1, 2 |
| Electrical (legacy 1.x) | Pass: 1; No Active: 2; No Gate Effect: 3; Open: 4 or →; Short: 5 | 1–5 already explicitly bound |

| Key | Action |
|---|---|
| ↑ / ↓ | Move by 1 visible row |
| Ctrl+↑ / Ctrl+↓ | Move by 10 visible rows |
| Shift+↑ / Shift+↓ | Move by 100 visible rows |
| Page Up / Page Down | Move by 1000 visible rows |
| ← | Revert each selected row to its current baseline |
| 0 / Delete | Clear each selected row's Status |
| Ctrl+O | Load an image folder |
| Ctrl+S | Save to Excel |
| Ctrl+L | Edit the label set |

Navigation stops at the first/last visible row. Letter shortcuts ignore Shift/Caps Lock. Help → Keyboard shortcuts displays the active set's keys.

In **Labels**, switch presets, edit the active set, import/export its JSON, or change the digit and auto-advance options. Sets contain 1–9 labels, each with a unique name, `#RRGGBB` color, optional description, and zero or more explicit tkinter key symbols. The editor supports adding/removing/reordering labels, changing colors, and capturing/removing keys. Editing a preset creates a custom set unless it is unchanged. Switching or renaming labels does not rewrite existing statuses.

Explicit keys take priority over numeric ordinals. For example, an explicit `2` bound to the first label overrides “2 means the second label.” Turning off ordinal keys leaves explicit digit bindings active, including the legacy preset's 1–5.

Reserved keys cannot be assigned to a label: Up, Down, Page Up (`Prior`), Page Down (`Next`), Left, Delete, 0, Escape, Return, Tab, Space, and Backspace. Right may be assigned. Ctrl combinations are not label shortcuts. Unknown existing statuses remain visible and use white row backgrounds; known labels use a lightened version of their configured color.

The active set, digit setting (initially on), and auto-advance setting (initially off) persist in `%APPDATA%\ImageMarker\config.json`. Image folders, source files, and session edits are not restored at startup. A missing or unreadable config falls back to defaults.

Auto-advance applies only to a single selection, including Clear and reapplying the same value. It does not advance after Revert or a multi-row edit. With an active filter, if the changed row disappears, the app first selects the next visible row and then advances again; turn auto-advance off when reviewing a queue whose edited rows leave the filter.

A label-set export has this shape; the top-level `name` names the **set**, and each `labels[].name` is the value written to Status:

```json
{
  "schema_version": 1,
  "name": "GOOD / BAD / OPEN",
  "labels": [
    {"name": "GOOD", "color": "#2e9e4f", "keys": ["g"]},
    {"name": "BAD", "color": "#d64545", "keys": ["b"]},
    {"name": "OPEN", "color": "#e8a33d", "keys": ["o"]}
  ]
}
```

## Filtering and unsaved changes

**Status filter** lists statuses currently present, including **(blank)** when applicable. All shows everything; None hides everything. Counts and navigation follow the visible view; the info bar also shows full-set counts and the unsaved count. Filtering affects visibility, not save scope. When statuses appear/disappear, the menu is rebuilt: retained choices keep their check state, and new values are checked by default.

A row is unsaved only while its current Status differs from its baseline. A folder-only session starts with a blank baseline; Excel and matching CSV loads set the baseline from their source; a successful save sets it to the saved value. Revert is not a history stack, and does not recover older saves. Reapplying the baseline also clears the `*` marker. Row text becomes bold while dirty, and the title displays an unsaved count.

Loading a folder, loading Excel/CSV, or closing with edits prompts Yes/No/Cancel. Yes saves first (Excel when attached, otherwise CSV); No proceeds without saving; Cancel stays. Canceling the CSV destination or a handled save error also stops the pending action. The unmatched Excel limitation above still applies.

## Run and build from source

For source use, install Python 3.9+ with tkinter and the runtime dependencies Pillow and openpyxl. Run these commands from the repository root in Command Prompt:

```bat
python -m venv .venv
.venv\Scripts\activate
python -m pip install -r requirements.txt
python main.py
```

In PowerShell, run `.\.venv\Scripts\python.exe main.py` after creating the environment and installing dependencies with that same interpreter; activation is optional. Importing `imagemarker.app` does not open a window.

`build.bat` creates/reuses `.venv`, installs runtime dependencies and PyInstaller, and builds the one-file windowed `dist\ImageMarker.exe` using `ImageMarker.spec` and `assets/icon.ico`.

After building the exe, `build_installer.bat` locates an Inno Setup 6 or 7 compiler and builds `dist\ImageMarker-Setup-2.0.0.exe` from `installer\ImageMarker.iss`. The installer offers English/Korean, defaults to per-user installation, adds a Start Menu shortcut, and offers a desktop icon. An all-users installation can also be chosen. Uninstall through Windows Settings → Apps.

For development validation:

```bat
python -m pip install pytest
python -m pytest tests -q
python -c "import imagemarker.app"
```

The IO/model/label-set tests use synthetic data. GUI smoke tests skip when tkinter/Pillow or a display are unavailable. See [SPEC](docs/SPEC.md) for implementation detail and test scope.

## Maintain the documentation

Edit `README.ko.md`, `README.md`, or `docs/SPEC.md`, then regenerate their HTML companions. Documentation generation requires Python 3.10+; its dependency is separate from the application requirements.

```bat
python -m pip install -r requirements-docs.txt
python scripts/build_docs.py
python scripts/build_docs.py --check
```

Each HTML file embeds its screenshot and works offline. Keep companion files in their relative folders to follow links between guides; GitHub source links need an internet connection. Use the browser's print command for PDF or paper output. The check command verifies source/output freshness, anchors, local links, and embedded images.
