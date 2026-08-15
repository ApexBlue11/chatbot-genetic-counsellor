"""
Minimal SVG rasteriser for developer preview.

Renders the specific element subset that ``analysis.pedigree_svg`` emits — rect,
circle, path (diamond/arrow), line, polyline and text — to a PNG via Pillow.
It parses the real SVG output rather than re-drawing from the layout object, so
what you look at is what the browser will be handed.

This exists purely so the render loop can be inspected without a browser or a
native cairo build. It is not a general SVG renderer.

    python tests/svg_preview.py                     # all fixtures + contact sheet
    python tests/svg_preview.py path/to/file.svg    # one file
"""

import glob
import os
import re
import sys
import xml.etree.ElementTree as ET

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PIL import Image, ImageDraw, ImageFont   # noqa: E402

SVG_NS = "{http://www.w3.org/2000/svg}"
SCALE = 2


def _font(size, bold=False):
    candidates = ["arialbd.ttf", "arial.ttf"] if bold else ["arial.ttf"]
    for name in candidates:
        try:
            return ImageFont.truetype(name, int(round(size)))
        except Exception:
            continue
    return ImageFont.load_default()


def _num(element, attr, default=0.0):
    try:
        return float(element.get(attr, default))
    except (TypeError, ValueError):
        return default


def _colour(value, default=None):
    if not value or value == "none":
        return default
    return value


def _tag(element):
    return element.tag.replace(SVG_NS, "")


def _draw_element(element, draw, scale, size):
    kind = _tag(element)
    stroke = _colour(element.get("stroke"))
    fill = _colour(element.get("fill"))
    width = max(1, int(round(_num(element, "stroke-width", 1) * scale)))

    def sx(v):
        return v * scale

    if kind == "rect":
        w, h = element.get("width", "0"), element.get("height", "0")
        if w.endswith("%") or h.endswith("%"):          # page background
            draw.rectangle([0, 0, size[0], size[1]], fill=fill or "#ffffff")
            return
        x, y = _num(element, "x"), _num(element, "y")
        box = [sx(x), sx(y), sx(x + float(w)), sx(y + float(h))]
        draw.rectangle(box, fill=fill, outline=stroke, width=width)

    elif kind == "circle":
        cx, cy, r = _num(element, "cx"), _num(element, "cy"), _num(element, "r")
        box = [sx(cx - r), sx(cy - r), sx(cx + r), sx(cy + r)]
        draw.ellipse(box, fill=fill, outline=stroke, width=width)

    elif kind == "line":
        pts = [sx(_num(element, "x1")), sx(_num(element, "y1")),
               sx(_num(element, "x2")), sx(_num(element, "y2"))]
        draw.line(pts, fill=stroke or "#000000", width=width)

    elif kind == "polyline":
        raw = element.get("points", "")
        pts = [(sx(float(a)), sx(float(b)))
               for a, b in (p.split(",") for p in raw.split() if "," in p)]
        if len(pts) >= 2:
            draw.line(pts, fill=stroke or "#000000", width=width, joint="curve")

    elif kind == "path":
        coords = [float(v) for v in re.findall(r"-?\d+\.?\d*", element.get("d", ""))]
        pts = [(sx(coords[i]), sx(coords[i + 1])) for i in range(0, len(coords) - 1, 2)]
        if len(pts) >= 3:
            draw.polygon(pts, fill=fill, outline=stroke)
            if stroke and width > 1:
                draw.line(pts + [pts[0]], fill=stroke, width=width)

    elif kind == "text":
        content = "".join(element.itertext())
        if not content:
            return
        size_px = _num(element, "font-size", 12)
        font = _font(size_px * scale, element.get("font-weight") in ("600", "700", "bold"))
        x, y = sx(_num(element, "x")), sx(_num(element, "y"))
        anchor = element.get("text-anchor", "start")
        bbox = draw.textbbox((0, 0), content, font=font)
        text_w = bbox[2] - bbox[0]
        if anchor == "middle":
            x -= text_w / 2
        elif anchor == "end":
            x -= text_w
        if element.get("dominant-baseline") == "central":
            y -= (bbox[3] - bbox[1]) / 2
        else:
            y -= size_px * scale          # SVG y is the baseline
        draw.text((x, y), content, fill=_colour(element.get("fill"), "#000000"), font=font)


def rasterise(svg_path, png_path=None, scale=SCALE):
    """Render one SVG file to a PNG and return the output path."""
    with open(svg_path, encoding="utf-8") as fh:
        root = ET.fromstring(fh.read())

    viewbox = [float(v) for v in root.get("viewBox", "0 0 800 600").split()]
    size = (int(viewbox[2] * scale), int(viewbox[3] * scale))
    image = Image.new("RGB", size, "white")
    draw = ImageDraw.Draw(image)

    for element in root.iter():
        if _tag(element) in ("svg", "defs", "marker", "title", "g", "desc"):
            continue
        # Marker geometry is defined inside <defs> and drawn by reference; skip it.
        if any(_tag(parent) in ("defs", "marker") for parent in root.iter()
               if element in list(parent)):
            continue
        try:
            _draw_element(element, draw, scale, size)
        except Exception as exc:                                  # noqa: BLE001
            print(f"  ! could not draw <{_tag(element)}>: {exc}")

    png_path = png_path or os.path.splitext(svg_path)[0] + ".png"
    os.makedirs(os.path.dirname(png_path) or ".", exist_ok=True)
    image.save(png_path)
    return png_path


def contact_sheet(png_paths, out_path, columns=3, pad=26, label_h=26):
    """Tile the rendered fixtures into one reviewable image."""
    images = [(os.path.splitext(os.path.basename(p))[0], Image.open(p)) for p in png_paths]
    if not images:
        return None
    rows = (len(images) + columns - 1) // columns
    cell_w = max(im.width for _, im in images) + pad
    cell_h = max(im.height for _, im in images) + pad + label_h

    sheet = Image.new("RGB", (cell_w * columns, cell_h * rows), "#111827")
    draw = ImageDraw.Draw(sheet)
    font = _font(20, bold=True)

    for index, (name, im) in enumerate(images):
        col, row = index % columns, index // columns
        ox, oy = col * cell_w, row * cell_h
        draw.text((ox + pad // 2, oy + 4), name, fill="#93c5fd", font=font)
        sheet.paste(im, (ox + pad // 2, oy + label_h))

    sheet.save(out_path)
    return out_path


def main():
    if len(sys.argv) > 1:
        for path in sys.argv[1:]:
            print("wrote", rasterise(path))
        return 0

    svgs = sorted(glob.glob(os.path.join("tests", "pedigree_out", "*.svg")))
    if not svgs:
        print("No SVGs found — run tests/test_pedigree_layout.py first.")
        return 1

    out_dir = os.path.join("tests", "pedigree_out", "png")
    pngs = []
    for svg in svgs:
        name = os.path.splitext(os.path.basename(svg))[0]
        pngs.append(rasterise(svg, os.path.join(out_dir, name + ".png")))
        print(f"  rendered {name}")

    sheet = contact_sheet(pngs, os.path.join(out_dir, "_contact_sheet.png"))
    print(f"\n{len(pngs)} PNG(s) in {out_dir}/")
    print(f"contact sheet: {sheet}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
