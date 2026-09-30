# ImageMarker 2.0.0 — Current implementation specification

This document describes the implementation in the 2.0.0 source. It is a reference for maintainers and reviewers, not a list of future requirements. For operating instructions, see [English README](../README.md), [Korean guide](../README.ko.md), and [Korean HTML guide](../README.ko.companion.html).

## Purpose and boundaries

ImageMarker is a Windows desktop review tool built with tkinter, Pillow, and openpyxl. A human examines existing per-device RGB slice PNGs alongside measurements and assigns/corrects a Status label. The initial label set is GOOD / BAD / OPEN; the active set can be changed.

The application does not create slices, identify defects automatically, compute electrical metrics, edit image files, or train/export a machine-learning model. It provides Excel Status write-back and a separate legacy label CSV export.

## Source layout

| File | Responsibility |
|---|---|
| `main.py` | Calls `imagemarker.app.main()` when run |
| `imagemarker/__init__.py` | Version `2.0.0` |
| `imagemarker/app.py` | Main tkinter window, sample-mapping dialog, source/save workflows, view refresh, key handling |
| `imagemarker/data_model.py` | ImageRecord, scan results, parsing/normalization, ImageStore filtering/sorting/joins |
| `imagemarker/excel_io.py` | Workbook loading, sample suggestions, backup and cell write-back |
| `imagemarker/csv_io.py` | CSV loading, label aliases, export |
| `imagemarker/label_sets.py` | Labels/presets, validation, hotkeys, JSON/config persistence |
| `imagemarker/label_dialogs.py` | Label-set editor and key-capture dialog |
| `tests/test_data_model.py` | Parsing, scan, status baseline, filtering, navigation, sorting, joins |
| `tests/test_excel_io.py` | Synthetic workbook loading, joins, backup, Status-only assignment, errors |
| `tests/test_label_sets.py` | Presets, key priority, validation, config/JSON, CSV normalization |
| `tests/test_app_smoke.py` | tkinter label keys/editor/preset/auto-advance smoke coverage |
| `assets/screenshot.png` | Existing main-window screenshot using synthetic sample data |
| `ImageMarker.spec`, `build.bat` | PyInstaller packaging |
| `installer/ImageMarker.iss`, `build_installer.bat` | Windows installer packaging |

Importing `imagemarker.app` creates no window. Runtime dependencies are Pillow and openpyxl; pytest and PyInstaller are development/packaging tools.

## Images and record identity

The full filename pattern is `^(.+)_rgb_(\d+)_(\d+)\.png$`, matched case-insensitively. The prefix is the record Name; digit groups become integer Row and Node. The code does not enforce a positive coordinate range, a fixed grid size, a `_slices` directory name, or a manifest.

`scan_image_folder` walks the chosen folder recursively using `os.walk` with sorted directory and file names. Identity is `(name, row, node)`, including the exact prefix spelling. The first identity encountered wins and keeps its actual file path. Later duplicate paths are counted. Records are initially sorted by Name, Row, Node. Folders containing matching filenames are counted in scan metadata, even if their images are duplicates.

A successful nonempty folder load replaces the store, detaches Excel and the displayed source path, resets CSV headers to the four base fields, and starts statuses/metrics blank. Initial store filter and sorting state reset. The filter-menu rebuild preserves check states for status names already present; it is not a guaranteed reset of every checkbox.

A filename can match even if the image is corrupt: decoding occurs on selection and an error appears on the canvas. Image loading does not remove its record.

Each ImageRecord holds the path, Status, original/baseline Status, six optional metrics, Excel cell coordinates when matched, an internal `no_data` flag, and preserved CSV extra fields. That internal flag has no dedicated table indicator.

## Main interface

The window starts at 1400×900 with a vertically draggable divider and image/table panes. The initial divider is approximately halfway down. Images are centered, preserve aspect ratio, and fit with a 0.95 scale margin; they may be enlarged as well as reduced.

Toolbar actions are Load Folder, Open Excel..., Save to Excel, Load CSV, Save CSV, and Status filter. Label buttons follow the active set, with additional Revert and Clear buttons. The interface and messages use English.

Table columns are an unlabeled dirty-marker column, Name, Row, Node, ON, OFF, ON/OFF, gm, Vth, Carrier Mobility, and Status. It has vertical/horizontal scrollbars and extended selection. The image follows the first selected record; edits affect the stored selected records, falling back to the current record if there is no explicit selection.

Dirty rows have a `*` marker and bold text. Known statuses use a lightened configured label color; blank/unknown statuses use white. An applied value may flash in large colored canvas text for approximately one second. Redrawing/navigation can clear that overlay earlier.

The info bar reports the position in the visible view; status counts (visible/full while filtered); filter description; folder/scan summary; source filename and Excel sample summary; and total unsaved count. The title gains an asterisk and unsaved count while dirty. The Save to Excel toolbar button is enabled only when Excel is attached and any record is dirty; this can include only unmatched records. Menu/key invocation performs its own checks.

## Normalization and displayed metrics

Status values normalize to trimmed strings or None for blank. Excel Status is not limited to a fixed enum, and is not renamed on load. CSV normalization is separate (see below).

Integer normalization accepts integral numbers and text such as `01` and `1.0`; booleans, fractional values, blanks, and unusable text are rejected. Numeric metrics use best-effort float conversion; blank/nonnumeric values display blank. Display is scientific notation with three digits after the decimal when `0 < abs(v) < 1e-3` or `abs(v) >= 1e5`, otherwise four significant digits. These are display rules, not workbook value modifications.

## Excel read and matching

The GUI accepts an `.xlsx` selection and invokes `ExcelSource.load(path)`. The loader uses openpyxl with `read_only=True, data_only=True`. The first worksheet is selected; the Python API can accept a sheet name, but the GUI has no picker.

Headers are on row 1. They are stripped and matched case-insensitively against:

`Name, Row, Node, ON, OFF, ON/OFF, gm, Vth, Carrier Mobility, Status`.

Only Name, Row, Node, and Status are required. Order is flexible; the first matching occurrence of a duplicate header is used. For data rows, iteration stops at the rightmost recognized column, not necessarily the first ten worksheet columns. The header is scanned across the worksheet. Extra sweep columns after the recognized columns are not materialized as measurements or displayed.

Empty rows and rows with an invalid Row or Node are skipped. Name is trimmed (a blank Name becomes an empty string). Worksheet row indices remain the actual 1-based positions despite skipped rows. Formula cells are read using cached results; the application does not recalculate formulas.

Distinct Excel Names and their parsed-row counts retain first-seen order. Automatic suggestion extracts the first sample number matching `sam\s*_?(\d+)`, case-insensitively, from each image prefix and Excel Name. A suggestion exists only if exactly one Excel Name shares that number. No exact-prefix or fuzzy similarity fallback is implemented.

The modal dialog shows every image prefix, its image count, and an Excel Name dropdown with (skip). The user can override each suggestion. Cancel leaves the existing source unchanged. If every sample is skipped, a warning appears and the new workbook is not attached.

Confirmed prefixes join to the chosen Name's rows by integer (Row, Node). First duplicate coordinate within that Excel Name wins. Matched records receive Status/baseline, metrics, and worksheet row/Status-column coordinates. Unmatched/skipped records have Status/baseline and metrics cleared, lose Excel coordinates, and become internally `no_data=True`.

The load summary shows sheet, per-prefix matched/unmatched counts, and totals. “Excel rows without an image” is calculated from indexes for the selected Names; it is not a count across every unselected sample in the workbook.

The mapping UI permits more than one image prefix to select the same Excel Name. Such records can share a write-back cell. Saving conflicting edits to a shared cell processes records in current store order, so the last assignment wins; map independent samples to their corresponding Names.

## Excel write-back and backup

Dirty records come from the full store, regardless of table filter or selection. Only records with remembered Excel row and Status-column positions generate updates. Unmatched records are counted as skipped.

For nonempty updates:

1. Copy `data.xlsx` to adjacent `data.backup.xlsx` using `shutil.copy2`, unless that backup already exists.
2. Reopen the original workbook through openpyxl in normal mode.
3. Locate the remembered worksheet name and assign normalized Status values to the remembered coordinates.
4. Save the original workbook path and close it.
5. Update corresponding in-memory Excel rows.

There is no backup on a no-op save, no recurring backup, and no backup refresh. The app assigns no other columns; tests cover retained synthetic formulas, values, and formatting. The whole workbook is nevertheless serialized through openpyxl, so “Status-only” describes cell assignments rather than a byte-preserving patch or a guarantee for every Excel-specific feature.

The code does not rematch headers/rows at save time. Keep the worksheet layout unchanged while attached; reload after external layout changes. Clearing a Status writes a blank cell.

Permission errors in opening, copying, or saving are surfaced as file-lock/permission messages with a retry instruction. Other recoverable Excel errors also appear in dialogs. Successfully written records adopt their saved value as baseline. Skipped records remain dirty; the regular save dialog reports updated/skipped counts and a newly created backup.

### Save-prompt limitation in 2.0.0

The save-before-close/source-change path also writes only records with Excel coordinates, but returns success after the write call even if skipped dirty records remain. It does not show the regular save's skipped-row summary. Therefore “Yes = save and close” or “Yes = save first” can proceed while edits on unmatched records have not been stored in Excel.

The user should perform a regular Excel save, inspect remaining Unsaved counts, and export unmatched edits with Save CSV before leaving, or Revert them intentionally. This is an implementation limitation, not an assurance that every dirty record was saved.

## CSV read, join, and export

The loader uses `csv.DictReader` with UTF-8 BOM support. Header matching is case-insensitive after trimming. Name/Row/Node identify rows. Label-column priority is label, then marker, then status. Missing required-looking headers do not raise a format error: missing Name becomes empty, missing/invalid coordinates become zero in keys, and a missing label is blank.

Loaded output headers normalize to `name,row,node,label` plus arbitrary nonbase input headers. Extra fields are preserved as strings for each key. Input duplicate keys overwrite earlier values/extras; the last occurrence wins.

Label normalization proceeds in this order:

1. None, empty strings, and case-insensitive NONE, N/A, NA, AMBIGUOUS, UNKNOWN, UNCLASSIFIED become blank.
2. Values equal to an active label name (case-insensitively) use its canonical spelling.
3. Legacy aliases apply only if their target label exists in the active set.
4. Other values are retained as trimmed strings.

Examples of legacy aliases are PASS/P/OK/GOOD/TRUE/YES/1 → Pass, NO ACTIVE/NOACTIVE/NO_ACT/INACTIVE → No Active, OPEN/OP/-1 → Open, and SHORT/SH → Short. Active-set matching takes precedence, so GOOD remains GOOD in the default set. Numeric CSV values are not ordinal shortcut positions. The no-label-set Python helper retains legacy behavior, but the GUI always supplies its active set.

CSV join uses exact `(name, row, node)` against loaded images. Matching rows receive Status/baseline and extras, and cease to be internally no-data. Unmatched images remain unchanged. The join does not clear old Excel metrics/cell coordinates or convert metric-like CSV extras to displayed metrics. After GUI CSV loading, the app detaches Excel and records the CSV path as the displayed source.

Save CSV:

- Always prompts for a destination, even when a CSV source is already loaded.
- Writes every loaded image record in current store order, including hidden/unchanged rows.
- Excludes input CSV rows without a loaded image counterpart.
- Writes base fields and the retained extra headers with UTF-8 BOM; blank label is an empty cell.
- Does not automatically add/export measurements from Excel.
- Uses normal file writing with no backup.
- On success commits the baseline for every record and clears all dirty markers.
- Does not change the displayed source path or detach an existing Excel source.

That last behavior affects mixed output workflows: CSV export commits labels in memory while Excel is still attached. A subsequent Save to Excel sees no dirty updates for them, although Excel was not changed. Save to Excel first, then export CSV when both are required. For a fresh replacement CSV dataset, reload the image folder before loading the CSV to avoid retaining unmatched old labels/data.

## Label sets and persistent settings

A LabelSet consists of a set name and 1–9 ordered LabelDefs. Each label has a name, `#RRGGBB` color, key list, and optional description. The top-level set name is metadata; the individual label name is what gets assigned to Status.

The shipped presets are:

| Set | Labels, colors, explicit keys |
|---|---|
| GOOD / BAD / OPEN (default) | GOOD `#2e9e4f` G; BAD `#d64545` B; OPEN `#e8a33d` O |
| PASS / FAIL | PASS `#2e9e4f` P; FAIL `#d64545` F |
| Electrical (legacy 1.x) | Pass `#5cc25c` 1; No Active `#4da6ff` 2; No Gate Effect `#c9b037` 3; Open `#ff6b6b` 4/Right; Short `#ff9800` 5 |

The editor supports adding/removing/reordering labels, changing name/description/color, and key capture/removal. Capturing a modifier alone is ignored; Escape cancels capture. Validation rejects empty set/label names, labels outside the 1–9 limit, label names containing newlines, case-insensitive duplicate names, invalid colors, reserved keys, and keys owned by multiple labels.

Reserved key symbols are Up, Down, Prior, Next, Left, Delete, 0, Escape, Return, Tab, space, and BackSpace. Right is available for labels. Single letters normalize to lowercase and match regardless of Shift/Caps Lock. Explicit label keys are checked before numeric ordinal fallback. Disabling digit ordinals does not disable explicitly bound digits.

Editing a preset yields a custom set unless its name and label definitions are unchanged. Import replaces the active set; export saves a standalone schema-version-1 JSON. Switching sets changes shortcuts and colors, not existing record statuses/baselines. Unknown statuses remain visible and unmodified; known status color matching ignores case.

AppConfig stores the active set, whether it is a preset, digit ordinals (initial True), and auto-advance (initial False). Default Windows path is `%APPDATA%\ImageMarker\config.json` (home fallback when APPDATA is absent). `IMAGEMARKER_CONFIG_DIR` overrides the directory. Non-Windows uses XDG_CONFIG_HOME or `~/.config/imagemarker`.

Config and label-set writes use UTF-8 JSON and replacement of a `.tmp` file. Missing/unreadable/malformed config generally falls back to defaults. Session folder/source/filter/selection/edits are not persisted. A settings write failure reports a warning while retaining the in-memory choice.

## Editing, selection, navigation, and filtering

All statuses can be changed; there is no “changeable labels” restriction. Label buttons/hotkeys apply the active set's canonical spelling to all selected records. Clear (0/Delete) sets None; Left/Revert restores each selected record's baseline. The baseline is blank after a folder-only load, the joined source value after Excel/matching CSV loading, and the committed value after saving. Revert is a single baseline restore, not a history undo.

Dirty state is derived from normalized current/baseline inequality. Reapplying the baseline or Revert clears dirty state automatically. Successful Excel saves commit only writable dirty records; CSV export commits all records.

Navigation uses the filtered list and clamps at the ends: Up/Down ±1, Ctrl+Up/Down ±10, Shift+Up/Down ±100, Page Up/Page Down ±1000. Ctrl+O loads a folder, Ctrl+S saves Excel, Ctrl+L edits labels. Generic label dispatch ignores events with Control held. Navigation that changes the current record makes it the single selection.

Auto-advance is optional and applies only with one selected target, after label or Clear actions. Even applying the same value advances. Revert and multi-selection do not auto-advance. If a changed row leaves a filter, refresh moves to the next visible record (or previous at the end), and then auto-advance moves again. Turn the option off for filtered queues where edits remove the current row.

Sorting operates on the master list; repeated clicks toggle direction. The current record and visible selected records are retained. Row/Node/metrics sort numerically; Name and Status use case-insensitive text keys. Ascending Status and metric sorts put blank/missing values last; descending reverses that placement. Dirty-marker sorting puts changed rows first in its initial direction. Status edits invalidate visible caches, but do not automatically re-sort the master list by Status.

The filter menu is based on values actually present, including None displayed as (blank). All selects every value; None selects none. Values are exact normalized Status strings, so separately spelled existing statuses can be separate filter entries even when their colors match case-insensitively. Retained check states survive a menu rebuild; new values default checked. Filtering changes the visible view only, never the records considered by a save.

After edits/filter changes, a hidden current record moves to the next visible one in master order, or the previous at the end. With no visible records, current selection/image is empty.

## Unsaved prompts and error handling

Before loading a folder or another Excel/CSV source, a dirty session prompts Yes (save first), No (continue discarding), or Cancel (stay). Close uses the analogous save-and-close choices. Save routes to Excel when attached and otherwise to Save CSV. Canceling the CSV destination or a handled save error stops the pending action. See the partial Excel-save limitation above.

There is no autosave or session recovery. The normal operations do not write image files. A file-open, folder-read, CSV-load/save, label JSON, or Excel error is reported by the relevant GUI dialog or canvas message.

## Packaging and validation

`build.bat` creates/reuses repository `.venv`, upgrades pip, installs requirements plus PyInstaller, and builds `ImageMarker.spec`. The spec produces one-file `dist/ImageMarker.exe`, console=False, bundles `assets/icon.ico`, and collects package submodules.

`build_installer.bat` requires that exe first and searches PATH and standard per-user/machine directories for Inno Setup 7 or 6. `installer/ImageMarker.iss` defines 2.0.0 and emits `dist/ImageMarker-Setup-2.0.0.exe`. It offers English/Korean, per-user default or optional all-users installation, Start Menu shortcuts, optional desktop icon, and uninstall registration.

Run `python -m pytest tests -q` and `python -c "import imagemarker.app"` from the repository root for development checks. Tests use synthetic workbook/image data rather than modifying measurement directories. GUI smoke tests skip if tkinter/Pillow or a display is unavailable; a skipped test is not GUI validation. Existing tests cover key/model/Excel behavior and selected GUI operations, not every source-switch, mixed CSV/Excel, or save-prompt sequence.
