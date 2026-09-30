# ImageMarker

> 한국어 문서: [README.ko.md](README.ko.md)

A Windows desktop tool for reviewing per-device RGB slice images and
assigning `Status` labels from a **configurable label set** (GOOD / BAD /
OPEN by default) directly against the lab's Excel spreadsheets (with legacy
CSV support retained).

## What it is

ImageMarker loads a folder of per-device image slices
(`<name>_rgb_<row>_<node>.png`) — **including every subfolder**, so a whole
measurement day of `<sample>_slices` folders opens in one go — shows each
image alongside its metrics in a sortable table, and lets a reviewer
quickly step through the set and assign a `Status` label with single
keystrokes. The labels themselves - their names, colours and hotkeys - come
from a label set you can switch, edit, import and export from the `Labels`
menu. When a source Excel workbook is loaded, edited statuses are
written back **in place** — only the `Status` cells of rows you actually
changed are touched; every other cell, formula, and format in the
workbook is left untouched.

## Features

- **Image + data review** — image canvas on top (aspect-ratio preserved,
  resizes with the window), full data table below (Name, Row, Node, ON,
  OFF, ON/OFF, gm, Vth, Carrier Mobility, Status); the two sections are
  separated by a draggable divider so you can freely resize either one.
- **Recursive folder loading** — "Load Folder" walks the selected folder
  *and every subfolder below it*, so pointing it at a day's measurement
  folder loads all of its `<sample>_slices` subfolders at once. If the
  same `(name, row, node)` image turns up in more than one subfolder the
  first one found wins (the walk is alphabetical, so this is
  deterministic) and the info bar reports how many duplicates were
  skipped.
- **Excel in-place Status update** — open the lab's `.xlsx` workbook and
  match each loaded sample to its `Name` in the sheet (several samples can
  be matched to their own `Name` in a single session), review/correct
  statuses, then "Save to Excel" writes back only the changed `Status`
  cells — across all matched samples at once. A one-time
  `<file>.backup.xlsx` safety copy is made before the very first write.
- **Status filtering** — a "Status filter" dropdown lists every distinct
  status value currently present (including a `(blank)` entry) with
  checkboxes, plus All/None quick actions; unchecked values are hidden
  from the table and from keyboard navigation.
- **Configurable label sets** — the `Labels` menu ships three presets:
  **GOOD / BAD / OPEN** (default, hotkeys `G` `B` `O`), **PASS / FAIL**
  (`P` `F`) and **Electrical (legacy 1.x)** (`Pass`, `No Active`,
  `No Gate Effect`, `Open`, `Short` on `1`–`5`, `→` = `Open`, exactly as
  ImageMarker 1.x). *Edit label set…* opens an editor where you add, rename,
  reorder and recolour labels and bind any number of hotkeys to each (press
  the key to capture it); duplicate names, duplicate keys and reserved
  navigation keys are rejected. Sets can be exported to / imported from a
  small JSON file so a team shares one definition, and the active set is
  remembered between sessions.
- **Keyboard-driven review** — navigate and relabel a large set of images
  without touching the mouse: up/down arrows move by 1/10/100/1000 rows,
  the label hotkeys (or digits `1`–`9`, which always follow the order of the
  set) apply a label to the current selection, `0`/`Delete` clear it and
  `←` undoes a mislabel by reverting the row to the label its source file
  holds (multi-select is supported — a label key applies to every selected
  row). An optional *auto-advance* moves to the next row after each label.
- **Label bar** — one coloured button per label (with its hotkeys) plus
  Revert / Clear, for mouse-driven review.
- **Visual feedback** — table rows are color-coded with the label's colour,
  and a large overlay flashes the label you just applied for one second.
- **Column sorting** — click a column header to sort (toggle
  ascending/descending); the current selection follows the item you were
  viewing across the re-sort.
- **Info bar** — shows current position, per-status counts (for both the
  full set and the active filter), folder name (plus the number of image
  subfolders walked and duplicates skipped), source file name, and the
  unsaved-change count.
- **Unsaved-change protection** — a row counts as unsaved for as long as
  its label differs from the one in the source file, so undoing an edit
  (with `←`, or by simply setting the original label again) also clears
  the row's unsaved state; the window title and a marker column show
  unsaved rows, and closing with unsaved changes prompts
  save / discard / cancel.
- **Legacy CSV support** — the original CSV workflow (`name,row,node,label`
  + arbitrary extra columns) from the prototype tool still works via its
  own load/save menu items.

## Requirements

- Windows
- Python 3.9+ (to run from source)
- Dependencies in `requirements.txt`: `pillow`, `openpyxl`

## Run from source

```bat
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

## Build Windows exe

A one-file, windowed (no console) build is produced with PyInstaller via
the included spec file.

```bat
build.bat
```

`build.bat` creates/reuses a local `.venv`, installs `requirements.txt`
plus `pyinstaller`, runs `pyinstaller ImageMarker.spec`, and prints the
path to the result:

```
dist\ImageMarker.exe
```

The build uses the icon at `assets/icon.ico` (already committed to the
repo — regenerate it with `python assets/make_icon.py` if you ever need
to change it).

### Installer

A Windows installer can be built on top of `dist\ImageMarker.exe` with
[Inno Setup 6](https://jrsoftware.org/isinfo.php):

```bat
build_installer.bat
```

`build_installer.bat` checks that `dist\ImageMarker.exe` exists (build it
first with `build.bat` if not), locates the Inno Setup 6 compiler
(`ISCC.exe`), and compiles `installer\ImageMarker.iss`, producing:

```
dist\ImageMarker-Setup-2.0.0.exe
```

The installer installs per-user by default (no administrator prompt,
though an admin/all-users install can be chosen instead), adds a Start
Menu shortcut, offers an optional desktop icon, and can be removed later
from Windows Settings → Apps like any other installed program.

## Keyboard shortcuts

### Navigation

| Key                | Action                    |
|---------------------|---------------------------|
| `↑` / `↓`           | Move selection by 1       |
| `Ctrl` + `↑` / `↓`  | Move selection by 10      |
| `Shift` + `↑` / `↓` | Move selection by 100     |
| `Page Up` / `Page Down` | Move selection by 1000 |

Navigation and the position counter operate on the currently filtered
view when a status filter is active.

### Labeling

Applies to the current row, or to every selected row when multiple rows
are selected. The label keys depend on the active label set (`Labels`
menu); the defaults are:

| Key             | GOOD / BAD / OPEN (default) | Electrical (legacy 1.x) |
|-----------------|-----------------------------|-------------------------|
| `G` / `1`       | GOOD                        | Pass (`1`)              |
| `B` / `2`       | BAD                         | No Active (`2`)         |
| `O` / `3`       | OPEN                        | No Gate Effect (`3`)    |
| `4`, `→`        | —                           | Open                    |
| `5`             | —                           | Short                   |
| `Left`          | revert to the original label | revert                 |
| `0` or `Delete` | clear / blank               | clear / blank           |

Digits `1`–`9` always select labels in the order of the active set (this
can be switched off in the `Labels` menu); letters work with or without
Shift/Caps Lock. `Left` does not assign a label — it puts each selected row
back to the label its source file holds (the value loaded from the Excel
workbook or CSV, or the value of the last successful save; blank for rows
with no source data), which also clears the row's unsaved marker.

`Ctrl+O` loads an image folder, `Ctrl+S` saves to Excel, `Ctrl+L` opens the
label set editor, and *Help → Keyboard shortcuts* lists the bindings of the
active set.

## Label sets

`Labels` menu:

- the three presets (radio items) — choosing one replaces the active set;
- **Edit label set…** — editor for the active set (a preset edited this way
  becomes a custom set; the presets themselves never change);
- **Import label set…** / **Export label set…** — JSON files like the one
  below;
- **Digit keys 1-9 select labels in order** and **Auto-advance to next row
  after labeling** toggles.

The active set and the two toggles are stored in
`%APPDATA%\ImageMarker\config.json`.

```json
{
  "schema_version": 1,
  "name": "GOOD / BAD / OPEN",
  "labels": [
    {"name": "GOOD", "color": "#2e9e4f", "keys": ["g"], "description": "Device looks functional"},
    {"name": "BAD",  "color": "#d64545", "keys": ["b"]},
    {"name": "OPEN", "color": "#e8a33d", "keys": ["o"]}
  ]
}
```

`name` is written verbatim to the `Status` cell; `keys` use tkinter key
names (`g`, `1`, `Right`, `F5`, `Insert`, …). Up to 9 labels per set. Status
values already present in a workbook that are not part of the active set are
kept and shown as they are (white rows) — the set only decides what the
hotkeys write and how known labels are coloured.

## Excel workflow

1. **Load Folder** — pick the folder holding the images. Subfolders are
   included, so selecting a whole measurement folder loads every
   `<sample>_slices` subfolder underneath it in one pass.
2. **Open Excel…** — pick the `.xlsx` workbook (the first sheet is used
   automatically).
3. **Match samples to Excel names** — because image file names and the
   Excel `Name` values don't share a common prefix, ImageMarker extracts
   the sample number from both and pre-selects the best match. A dialog
   then shows one row per loaded sample (image name prefix, image count,
   and an Excel `Name` dropdown) so you can confirm or change each pairing
   — several samples can be matched to their own `Name` in one session,
   and any sample with no counterpart in the workbook can be set to
   `(skip)`. Each sample's rows are then joined to its images by
   `(Row, Node)` within its own `Name`, and a summary reports the
   matched / unmatched counts per sample.
4. **Review / edit** — matched rows populate the metric columns (ON, OFF,
   ON/OFF, gm, Vth, Carrier Mobility) and existing `Status`; rows with no
   matching Excel data are flagged and left blank. Correct statuses with
   the keyboard shortcuts above.
5. **Save to Excel** — enabled once there are unsaved changes. On first
   save, a `<file>.backup.xlsx` copy is made next to the source workbook
   (one-time safety backup). The original file is then reopened and only
   the `Status` cells of the rows you changed are updated and saved —
   nothing else in the workbook (other columns, the ~201 sweep-data
   columns, formatting) is modified. If the file is open in Excel, a
   message box asks you to close it and retry.

No other Excel column is ever edited by this tool, and no image files are
ever modified.

## Legacy CSV support

The original CSV workflow from the prototype (`name,row,node,label`, plus
any extra columns) is kept working via its own load/save menu items, for
folders that don't have an Excel workbook. Labels are read in the active
set's spelling (`good` → `GOOD`); the 1.x aliases (`1` → `Pass`,
`-1` → `Open`, `ok` → `Pass`, …) are only applied when the aliased label
exists in the active set, so `GOOD` is no longer silently turned into
`Pass`.

## Screenshots

![ImageMarker 2.0 main window (synthetic sample data)](assets/screenshot.png)

_Main window with the default GOOD / BAD / OPEN set: image canvas, label
bar, hint line and the colour-coded data table (synthetic sample data)._
