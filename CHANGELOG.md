# Changelog

## 2.0.1 - 2026-09-30

### Changed
- Make the RGB-only workflow explicit in the folder button, File menu,
  folder picker, shortcut help, and About text. One RGB PNG per device is
  sufficient; there is no IR selector, pairing step, or second image pane.
  The existing single-image loader continues to ignore obsolete `_ir_` files.
- Update the Markdown and offline HTML guides for the RGB-only workflow.

### Fixed
- Keep the current images, labels, selection, and data source when an empty
  or IR-only folder is selected. Previously the store was cleared while the
  old table and image remained visible. Validate the candidate folder before
  asking about unsaved changes or replacing the session.

### Validation
- Add regression coverage for RGB-only and mixed RGB/IR folders, one-image
  rendering, navigation and CSV export, and rejected/canceled folder loads.

## 2.0.0 - 2026-09-30

### Changed
- **Default label set is now GOOD / BAD / OPEN** (hotkeys `G` `B` `O`, or
  `1` `2` `3`) to match the optical-inspection classes of the CNT TFT study.
  The 1.x electrical statuses remain available as the *Electrical (legacy
  1.x)* preset with the same keys (`1`–`5`, `→` = `Open`).
- Label sets are configurable: a `Labels` menu with presets, an editor
  (names, colours, any number of hotkeys per label, ordering), JSON
  import/export, and persistence in `%APPDATA%\ImageMarker\config.json`.
- Table row colours, the overlay flash, the hint line and a new label
  button bar all follow the active set.
- CSV label parsing is label-set aware; the 1.x aliases (`1` → `Pass`,
  `good` → `Pass`, …) are only applied when the aliased label exists in the
  active set.
- New app icon (grid of labelled patches).
- `Ctrl+O` / `Ctrl+S` / `Ctrl+L` accelerators, *Help → Keyboard shortcuts*,
  optional auto-advance after labeling, optional digit-ordinal keys.

### Fixed
- Loading a legacy CSV containing `GOOD` no longer rewrites it as `Pass`.

### Compatibility
- The `Status` strings written to Excel are the label names of the active
  set; workbooks labelled with the 1.x statuses are still read and shown
  unchanged.
- Python 3.9+ as before; no new dependencies.

## 1.3.0

Last release of the fixed five-status version.
