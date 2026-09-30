"""Generate assets/icon.ico for the ImageMarker application.

Concept (v2): ImageMarker steps through a *grid* of device-patch images and
stamps a *label* on each one.  The icon therefore shows a dark rounded tile
holding a 3x3 grid of small image patches, three of which are already
labelled in the default GOOD / BAD / OPEN colours (green, red, amber), with a
white "current cell" frame on one patch - the reviewer's cursor.

Rendered at high resolution and downsampled into the standard Windows icon
sizes (16, 24, 32, 48, 64, 128, 256) so it stays crisp in the taskbar,
Explorer views and the Start menu.

Usage:
    python assets/make_icon.py [--preview]

Output:
    assets/icon.ico       (and assets/icon_preview.png with --preview)
"""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw

SUPERSAMPLE = 1024
ICON_SIZES = [16, 24, 32, 48, 64, 128, 256]

BG_TOP = (31, 41, 55)          # slate, top of the background gradient
BG_BOTTOM = (17, 24, 39)       # slate, bottom
PATCH_BASE = (203, 213, 225)   # unlabelled patch (light grey-blue)
PATCH_DEVICE = (100, 116, 139) # the little "electrode" glyph inside a patch
GOOD = (46, 158, 79)           # #2e9e4f - matches the GOOD label colour
BAD = (214, 69, 69)            # #d64545 - BAD
OPEN = (232, 163, 61)          # #e8a33d - OPEN
CURSOR = (255, 255, 255)

# Which grid cells carry which colour (row, col) -> colour.
LABELLED = {
    (0, 0): GOOD, (0, 1): GOOD, (0, 2): BAD,
    (1, 0): OPEN, (1, 1): GOOD,
}
CURSOR_CELL = (1, 2)


def _gradient_background(size: int, radius: float) -> Image.Image:
    """Rounded square filled with a vertical gradient."""
    gradient = Image.new("RGBA", (size, size), BG_TOP + (255,))
    draw = ImageDraw.Draw(gradient)
    for y in range(size):
        t = y / max(1, size - 1)
        color = tuple(round(a + (b - a) * t) for a, b in zip(BG_TOP, BG_BOTTOM)) + (255,)
        draw.line([(0, y), (size, y)], fill=color)
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, size - 1, size - 1], radius=radius, fill=255)
    out = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    out.paste(gradient, (0, 0), mask)
    return out


def _draw_device_glyph(draw: ImageDraw.ImageDraw, box, color) -> None:
    """A tiny printed-transistor glyph: two electrode bars and a channel gap."""
    x0, y0, x1, y1 = box
    w = x1 - x0
    h = y1 - y0
    bar_w = w * 0.28
    gap = w * 0.16
    top = y0 + h * 0.28
    bottom = y1 - h * 0.28
    cx = (x0 + x1) / 2
    draw.rounded_rectangle([cx - gap / 2 - bar_w, top, cx - gap / 2, bottom], radius=w * 0.05, fill=color)
    draw.rounded_rectangle([cx + gap / 2, top, cx + gap / 2 + bar_w, bottom], radius=w * 0.05, fill=color)
    # gate line across the middle
    draw.rectangle([x0 + w * 0.12, (top + bottom) / 2 - h * 0.04, x1 - w * 0.12, (top + bottom) / 2 + h * 0.04], fill=color)


def draw_icon(size: int) -> Image.Image:
    margin = size * 0.04
    radius = size * 0.20
    img = _gradient_background(size, radius)
    # keep the margin transparent so the tile does not touch the icon bounds
    frame = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    inner = img.resize((int(size - 2 * margin), int(size - 2 * margin)), Image.LANCZOS)
    frame.paste(inner, (int(margin), int(margin)))
    img = frame
    draw = ImageDraw.Draw(img)

    # 3x3 grid of patches
    grid_margin = size * 0.17
    gap = size * 0.035
    cell = (size - 2 * grid_margin - 2 * gap) / 3
    patch_radius = cell * 0.18
    for row in range(3):
        for col in range(3):
            x0 = grid_margin + col * (cell + gap)
            y0 = grid_margin + row * (cell + gap)
            box = [x0, y0, x0 + cell, y0 + cell]
            fill = LABELLED.get((row, col), PATCH_BASE)
            draw.rounded_rectangle(box, radius=patch_radius, fill=fill)
            glyph = CURSOR if (row, col) in LABELLED else PATCH_DEVICE
            _draw_device_glyph(draw, box, glyph)

    # cursor frame on the "current" cell
    row, col = CURSOR_CELL
    x0 = grid_margin + col * (cell + gap)
    y0 = grid_margin + row * (cell + gap)
    inset = -gap * 0.55
    width = max(2, int(size * 0.028))
    draw.rounded_rectangle(
        [x0 + inset, y0 + inset, x0 + cell - inset, y0 + cell - inset],
        radius=patch_radius + gap * 0.5,
        outline=CURSOR,
        width=width,
    )
    return img


def main() -> None:
    out_dir = Path(__file__).resolve().parent
    out_path = out_dir / "icon.ico"

    base = draw_icon(SUPERSAMPLE)
    frames = [base.resize((s, s), Image.LANCZOS) for s in ICON_SIZES]
    # Pillow writes every requested size from the largest frame; passing the
    # pre-scaled frames via append_images keeps our LANCZOS downsampling.
    frames[-1].save(
        out_path,
        format="ICO",
        sizes=[(s, s) for s in ICON_SIZES],
        append_images=frames[:-1],
    )
    print(f"Wrote {out_path} with sizes {ICON_SIZES}")

    if "--preview" in sys.argv:
        preview = out_dir / "icon_preview.png"
        base.resize((256, 256), Image.LANCZOS).save(preview)
        print(f"Wrote {preview}")


if __name__ == "__main__":
    main()
