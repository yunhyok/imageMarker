# ImageMarker

> 한국어 문서: [README.ko.md](README.ko.md)

A Windows desktop tool for reviewing per-device RGB slice images and
correcting their `Status` labels directly against the lab's Excel
spreadsheets (with legacy CSV support retained).

## What it is

ImageMarker loads a folder of per-device image slices
(`<name>_rgb_<row>_<node>.png`), shows each image alongside its metrics in
a sortable table, and lets a reviewer quickly step through the set and
correct the `Status` label with single keystrokes. When a source Excel
workbook is loaded, edited statuses are written back **in place** —
only the `Status` cells of rows you actually changed are touched; every
other cell, formula, and format in the workbook is left untouched.

## Features

- **Image + data review** — image canvas on top (aspect-ratio preserved,
  resizes with the window), full data table below (Name, Row, Node, ON,
  OFF, ON/OFF, gm, Vth, Carrier Mobility, Status).
- **Excel in-place Status update** — open the lab's `.xlsx` workbook,
  confirm which `Name` in the sheet corresponds to the loaded image
  folder, review/correct statuses, then "Save to Excel" writes back only
  the changed `Status` cells. A one-time `<file>.backup.xlsx` safety copy
  is made before the very first write.
- **Status filtering** — a "Status filter" dropdown lists every distinct
  status value currently present (including a `(blank)` entry) with
  checkboxes, plus All/None quick actions; unchecked values are hidden
  from the table and from keyboard navigation.
- **Keyboard-driven review** — navigate and relabel a large set of images
  without touching the mouse: arrow keys move by 1/10/100/1000 rows,
  number keys apply a status to the current selection (multi-select is
  supported — a label key applies to every selected row).
- **Visual feedback** — table rows are color-coded by status, and a large
  overlay flashes the status you just applied for one second.
- **Column sorting** — click a column header to sort (toggle
  ascending/descending); the current selection follows the item you were
  viewing across the re-sort.
- **Info bar** — shows current position, per-status counts (for both the
  full set and the active filter), folder name, source file name, and the
  unsaved-change count.
- **Unsaved-change protection** — every edit is tracked with a dirty flag;
  the window title and a marker column show unsaved rows, and closing with
  unsaved changes prompts save / discard / cancel.
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
dist\ImageMarker-Setup-1.0.0.exe
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

### Status labeling

Applies to the current row, or to every selected row when multiple rows
are selected.

| Key             | Status set        |
|------------------|--------------------|
| `Left`           | No Active          |
| `Right`          | Open               |
| `1`              | Pass               |
| `2`              | No Active          |
| `3`              | No Gate Effect     |
| `4`              | Open               |
| `5`              | Short              |
| `0` or `Delete`  | (clear / blank)    |

## Excel workflow

1. **Open Excel…** — pick the `.xlsx` workbook (the first sheet is used
   automatically).
2. **Choose the sample Name** — because the image folder name and the
   Excel `Name` values don't share a common prefix, ImageMarker extracts
   the sample number from both and pre-selects the best match; a small
   dialog lets you confirm (or pick a different) `Name` before rows are
   joined to the loaded images by `(Row, Node)`.
3. **Review / edit** — matched rows populate the metric columns (ON, OFF,
   ON/OFF, gm, Vth, Carrier Mobility) and existing `Status`; rows with no
   matching Excel data are flagged and left blank. Correct statuses with
   the keyboard shortcuts above.
4. **Save to Excel** — enabled once there are unsaved changes. On first
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
folders that don't have an Excel workbook.

## Screenshots

_placeholder — add a screenshot of the main window here (image canvas,
data table, and status filter dropdown)._
