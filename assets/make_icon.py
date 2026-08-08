"""Generate assets/icon.ico for the ImageMarker application.

Draws a simple flat icon: a rounded-square background, a white "photo
frame" glyph (mountain + sun, representing an image), and a small colored
tag/label badge in the corner (representing the Status label that this
tool edits). Rendered at high resolution and downsampled into the standard
Windows icon sizes (16, 32, 48, 256) so the final .ico looks crisp at every
size Windows uses (taskbar, Explorer list/detail view, large icons, etc.).

Usage:
    python assets/make_icon.py

Output:
    assets/icon.ico
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

# Render large, then downsample for crisp anti-aliased results at small sizes.
SUPERSAMPLE = 512
ICON_SIZES = [16, 32, 48, 256]

# Flat color palette
BG_COLOR = (37, 99, 235, 255)  # flat blue, rounded-square background
FRAME_COLOR = (255, 255, 255, 255)  # white photo frame
FRAME_INNER_COLOR = (191, 219, 254, 255)  # pale blue "sky" inside the frame
MOUNTAIN_COLOR = (37, 99, 235, 255)  # same blue as background, for contrast
SUN_COLOR = (255, 255, 255, 255)
TAG_COLOR = (249, 115, 22, 255)  # flat orange status-tag badge
TAG_DOT_COLOR = (255, 255, 255, 255)


def _draw_icon(size: int) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    margin = size * 0.06
    radius = size * 0.22
    draw.rounded_rectangle(
        [margin, margin, size - margin, size - margin],
        radius=radius,
        fill=BG_COLOR,
    )

    # "Photo" frame, inset within the rounded square
    frame_margin = size * 0.20
    frame_box = [frame_margin, frame_margin, size - frame_margin, size - frame_margin * 1.15]
    frame_radius = size * 0.05
    draw.rounded_rectangle(frame_box, radius=frame_radius, fill=FRAME_COLOR)

    inner_pad = size * 0.035
    inner_box = [
        frame_box[0] + inner_pad,
        frame_box[1] + inner_pad,
        frame_box[2] - inner_pad,
        frame_box[3] - inner_pad,
    ]
    inner_radius = max(frame_radius - inner_pad, 0)
    draw.rounded_rectangle(inner_box, radius=inner_radius, fill=FRAME_INNER_COLOR)

    # Clip subsequent glyph drawing to the inner "photo" area using a mask.
    mask = Image.new("L", (size, size), 0)
    mask_draw = ImageDraw.Draw(mask)
    mask_draw.rounded_rectangle(inner_box, radius=inner_radius, fill=255)

    glyph_layer = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    glyph_draw = ImageDraw.Draw(glyph_layer)

    # Sun (small circle, upper-left of the photo)
    sun_r = (inner_box[2] - inner_box[0]) * 0.12
    sun_cx = inner_box[0] + (inner_box[2] - inner_box[0]) * 0.28
    sun_cy = inner_box[1] + (inner_box[3] - inner_box[1]) * 0.32
    glyph_draw.ellipse(
        [sun_cx - sun_r, sun_cy - sun_r, sun_cx + sun_r, sun_cy + sun_r],
        fill=SUN_COLOR,
    )

    # Mountains (two overlapping triangles) along the bottom of the photo
    ih0, iw0, ih1, iw1 = inner_box[1], inner_box[0], inner_box[3], inner_box[2]
    base_y = ih1
    peak_y = ih0 + (ih1 - ih0) * 0.30

    # Back (smaller) peak
    glyph_draw.polygon(
        [
            (iw0 + (iw1 - iw0) * 0.55, peak_y + (ih1 - ih0) * 0.10),
            (iw0 + (iw1 - iw0) * 0.80, base_y),
            (iw0 + (iw1 - iw0) * 0.35, base_y),
        ],
        fill=MOUNTAIN_COLOR,
    )
    # Front (larger) peak
    glyph_draw.polygon(
        [
            (iw0 + (iw1 - iw0) * 0.30, peak_y),
            (iw0 + (iw1 - iw0) * 0.62, base_y),
            (iw0 - (iw1 - iw0) * 0.05, base_y),
        ],
        fill=MOUNTAIN_COLOR,
    )

    img.paste(glyph_layer, (0, 0), Image.composite(glyph_layer, Image.new("RGBA", (size, size), (0, 0, 0, 0)), mask))

    # Status "tag" badge: small colored circle with a lighter dot, bottom-right
    # corner, representing the editable Status label this tool assigns.
    tag_r = size * 0.155
    tag_cx = size - margin - tag_r * 0.55
    tag_cy = size - margin - tag_r * 0.55
    ring_w = max(size * 0.02, 1.5)
    draw.ellipse(
        [tag_cx - tag_r, tag_cy - tag_r, tag_cx + tag_r, tag_cy + tag_r],
        fill=TAG_COLOR,
        outline=FRAME_COLOR,
        width=int(ring_w),
    )
    dot_r = tag_r * 0.30
    draw.ellipse(
        [tag_cx - dot_r, tag_cy - dot_r, tag_cx + dot_r, tag_cy + dot_r],
        fill=TAG_DOT_COLOR,
    )

    return img


def main() -> None:
    out_dir = Path(__file__).resolve().parent
    out_path = out_dir / "icon.ico"

    base = _draw_icon(SUPERSAMPLE)

    resized = [base.resize((s, s), Image.LANCZOS) for s in ICON_SIZES]
    largest = resized[-1]
    largest.save(
        out_path,
        format="ICO",
        sizes=[(s, s) for s in ICON_SIZES],
    )
    print(f"Wrote {out_path} with sizes {ICON_SIZES}")


if __name__ == "__main__":
    main()
