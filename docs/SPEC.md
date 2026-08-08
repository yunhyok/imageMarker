# ImageMarker — Windows Application Specification

## Purpose
Desktop tool for reviewing per-device RGB slice images and correcting their labels
(Status). Existing prototype: `V:\samples\imageMarker.py` (tkinter, CSV-only).
This project converts it into a structured Windows application with Excel support
and status filtering.

## Source data facts (verified)

### Image folders
- Images live in folders like `V:\samples\20260619 low yield\<sample name>_slices\`
- Filename pattern: `<name>_rgb_<row>_<node>.png` (row/node zero-padded, e.g. `_rgb_01_07.png`)
- One `_slices` folder = one sample (~989 files: 988 images, rows 1..26, nodes 1..38,
  plus a `_slice_manifest.json`)
- A measurement folder holds SEVERAL `_slices` subfolders (e.g. four to five
  samples side by side), so "Load Folder" must scan RECURSIVELY and can end up
  holding several distinct image name prefixes at once.

### Excel format (new, must support)
- Example: `V:\samples\20260619 low yield\20260619_low_yield_150px_data.xlsx`
- Single sheet (name varies, e.g. `150px_20260619`), header on row 1
- Columns (in order): `Name, Row, Node, ON, OFF, ON/OFF, gm, Vth, Carrier Mobility, Status`,
  then ~201 numeric sweep columns (`-20.00000` … `20.00000`) — sweep columns are
  NEVER displayed and NEVER modified.
- ~3952 data rows; `Name` has multiple distinct values (one per sample, e.g.
  `20260619-P3MEEMT(1-3)_7kgf_100_sam1` … `sam4`), each with ~988 rows.
- `Row` cells may be stored as TEXT with leading zeros (`'01'`) or as numbers —
  normalize both to `int`. `Node` is int 1..38.
- `Status` values observed: `Pass`, `No Gate Effect`, `No Active`, and blank/None
  (~half the rows are blank). Treat the value set as OPEN-ENDED — collect unique
  values dynamically, never hardcode-reject unknown values.
- CRITICAL: image-folder name prefix does NOT match Excel `Name`
  (`260619 p3meet ac 7kg 100mm, SAM 1` vs `20260619-P3MEEMT(1-3)_7kgf_100_sam1`).
  Matching Excel rows to images therefore works like this:
  1. On Excel load, list distinct `Name` values with row counts, and collect the
     distinct image name prefixes of the loaded records (a recursive load holds
     one prefix per sample).
  2. Auto-suggest the best match PER IMAGE PREFIX by extracting a sample number
     (regex `sam\s*_?(\d+)` case-insensitive) from both the image name prefix and
     each Excel Name; if exactly one Excel Name shares the number, preselect it.
  3. Show a mapping dialog with one row per image prefix
     (prefix, image count, Excel-`Name` combobox preselected with the suggestion,
     `(skip)` for "no counterpart in this workbook") + OK/Cancel. With a single
     prefix the dialog simply has one row.
  4. Then match rows by `(row, node)` ints within each prefix's mapped Name.
     Records mapped to different Names coexist in one session; write-back is
     per record (worksheet row + Status column) so they can all be dirty and
     saved together.

### Legacy CSV format (keep working)
- Columns `name,row,node,label` (+ arbitrary extra columns preserved on save),
  as implemented in the prototype. Keep the load/save CSV features as-is
  (menu items), including `parse_label_value` normalization.

## Application requirements

### Structure (package layout)
```
imageMarker/
  main.py                  # entry point: from imagemarker.app import main; main()
  imagemarker/
    __init__.py            # __version__ = "1.0.0"
    app.py                 # tkinter UI (ImageMarkerApp), main()
    data_model.py          # ImageRecord dataclass, recursive folder scan
                           # (scan_image_folder -> FolderScanResult), ImageStore
                           # (list mgmt, filtering, sorting)
    excel_io.py            # ExcelSource class (load/update-in-place)
    csv_io.py              # legacy CSV load/save helpers
  tests/
    test_excel_io.py       # pytest, uses synthetic workbook built in tmp_path
    test_data_model.py
  docs/SPEC.md             # this file
```

### Core behaviors (carried over from prototype)
- Load image folder → walk it RECURSIVELY (`os.walk`, sorted dirnames/filenames
  for a deterministic order), parse `<name>_rgb_<row>_<node>.png` in every
  subfolder, sorted by (name,row,node). Each record keeps the actual path of the
  file it was found at. A repeated `(name,row,node)` keeps the first file
  encountered; the rest are counted and the count is reported in the post-load
  summary (info bar).
- Image canvas on top (aspect-ratio preserved, resizes with window), table
  below, the two sections split by a draggable sash (`tk.PanedWindow`) so
  either can be freely resized
- Table columns: Name, Row, Node, ON, OFF, ON/OFF, gm, Vth, Carrier Mobility, Status
  (metric columns empty until an Excel/CSV is loaded; keep widths sensible)
- Keyboard: ↑/↓ navigate ±1, Ctrl ±10, Shift ±100, PgUp/PgDn ±1000
- Multi-select in table; label keys apply to all selected rows
- Row background colors by status: No Active → lightblue, Open → lightcoral,
  No Gate Effect → khaki, Pass → pale green (#d8f0d8), blank/None → white
- Large overlay text flashes the applied status for 1 s (colored accordingly)
- Column-click sorting (toggle asc/desc); after sorting, selection follows the
  currently viewed item (fix the prototype bug where current_index pointed to the
  wrong item after sort)
- Info bar: current position, per-status counts (of the FULL set and of the
  filtered view when a filter is active), folder name, source file name,
  unsaved-change count

### Status editing
- Any row's status may be changed (the prototype's changeable_labels restriction
  is REMOVED — this tool's purpose is correcting already-assigned labels).
- Keys: Left = `No Active`, Right = `Open` (compat);
  `1`=Pass, `2`=No Active, `3`=No Gate Effect, `4`=Open, `5`=Short,
  `0` or Delete = clear (blank).
- Every change sets a per-record `dirty` flag (cleared only on successful save).
  Dirty rows show a `*` marker column or bold text; window title shows `*` and
  unsaved count. Closing the window with unsaved changes prompts
  save / discard / cancel.

### Excel integration (new)
- "Open Excel…" button/menu: pick .xlsx → sheet auto = first sheet.
- Read with openpyxl read_only mode for speed; only the first 10 columns are
  materialized per row, PLUS remember for each record its 1-based worksheet row
  index and the Status column index — this is what makes targeted write-back
  possible.
- After the name-mapping dialog (see above), join each image prefix's records by
  (row, node) within its mapped Excel Name. Report matched/unmatched counts per
  prefix plus a total. Records with no Excel row (unmatched, or a skipped prefix)
  keep blank metrics and get flagged `no_data`.
- Metric display formatting: scientific notation `%.3e` when 0 < |v| < 1e-3 or
  |v| >= 1e5, else up to 4 significant digits; blank for None.
- "Save to Excel" button/menu (enabled only when an Excel is loaded and dirty
  records exist):
  1. If `<file>.backup.xlsx` does not exist next to the source, copy the source
     to it first (one-time safety backup).
  2. Re-open the ORIGINAL file with openpyxl (normal mode, keep formatting),
     set ONLY the Status cells of dirty records (by remembered row index and
     Status column), save in place. Nothing else in the workbook is touched.
  3. Handle PermissionError (file open in Excel) with a clear message box telling
     the user to close the file and retry.
  4. On success clear dirty flags and refresh UI.

### Filter feature (new)
- Toolbar area "Status filter": a Menubutton dropdown containing one checkbox per
  distinct status value currently present (computed dynamically, including
  `(blank)` for empty), plus "All" / "None" quick actions. Default: all checked.
- Unchecking values hides those rows from the table; navigation (arrow keys) and
  position counter operate on the FILTERED list.
- After a status edit, the filter is re-applied immediately; if the current row
  no longer matches, selection moves to the next visible row (or previous if at
  end). The dropdown's value set refreshes when new values appear.
- Filter state also shown in the info bar, e.g. `Filter: No Active, (blank) — 231/3952`.

### Non-goals
- No editing of any Excel column other than Status.
- No modification of image files.
- Original prototype file `V:\samples\imageMarker.py` and everything under
  `V:\samples\` must NOT be modified by this project or its tests.

## Packaging (Windows application)
- PyInstaller one-file windowed build: `ImageMarker.exe`
  - `ImageMarker.spec` checked into repo (name `ImageMarker`, `console=False`,
    icon `assets/icon.ico`)
  - `build.bat`: creates/uses `.venv`, installs `requirements.txt` +
    `pyinstaller`, runs `pyinstaller ImageMarker.spec`, output in `dist\`
  - `assets/make_icon.py`: generates a simple flat icon (Pillow) → `icon.ico`,
    committed so builds don't require regenerating
- `requirements.txt`: `pillow`, `openpyxl` (pandas NOT required at runtime)
- `.gitignore`: `__pycache__/`, `.venv/`, `build/`, `dist/`, `*.spec.bak`,
  `*.xlsx`, `*.png` test artifacts, `Thumbs.db`
- `README.md` (English): overview, screenshots placeholder, install/run from
  source, build instructions, keyboard reference table, Excel workflow
  description. (Korean translation `README.ko.md` is produced separately.)

## Quality bar
- Tests must pass with `python -m pytest tests -q` (no GUI needed for io/model tests).
- `python -c "import imagemarker.app"` must succeed (no side effects on import).
- Type hints on public functions; no global state outside the App class.
