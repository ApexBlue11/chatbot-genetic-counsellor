"""
SVG renderer for a resolved :class:`~analysis.pedigree_layout.PedigreeLayout`.

Output follows standard clinical pedigree notation — square/circle/diamond for
male/female/unknown, filled for affected, centre dot for carrier, diagonal slash
for deceased, arrow for the proband — drawn black on white so a counselor can
print it. All layout decisions are made upstream; this module only draws.

Every string that originates from the model is XML-escaped, since the rendered
SVG is handed to the browser.
"""

from typing import List, Optional
from xml.sax.saxutils import escape

from analysis.pedigree_layout import (
    AGE_FONT, LABEL_TOP_PAD, LINE_HEIGHT, NAME_FONT, PedigreeLayout, NodeBox,
    Segment, text_width,
)

STROKE = "#111827"
TEXT = "#1f2937"
MUTED = "#6b7280"
LINE = "#374151"
PAPER = "#ffffff"
ACCENT = "#4f46e5"

STROKE_WIDTH = 2.0
CONNECTOR_WIDTH = 1.6


def _fmt(value: float) -> str:
    """Trim coordinates to 2dp and drop trailing zeros — keeps the SVG small."""
    text = f"{value:.2f}".rstrip("0").rstrip(".")
    return text if text not in ("", "-0") else "0"


def _symbol(node: NodeBox) -> List[str]:
    """The base shape, filled according to disease status."""
    half = node.size / 2
    affected = node.status == "affected"
    fill = STROKE if affected else PAPER
    x, y = node.x, node.y
    parts: List[str] = []

    if node.gender == "male":
        parts.append(
            f'<rect x="{_fmt(x - half)}" y="{_fmt(y - half)}" '
            f'width="{_fmt(node.size)}" height="{_fmt(node.size)}" '
            f'fill="{fill}" stroke="{STROKE}" stroke-width="{STROKE_WIDTH}"/>'
        )
    elif node.gender == "female":
        parts.append(
            f'<circle cx="{_fmt(x)}" cy="{_fmt(y)}" r="{_fmt(half)}" '
            f'fill="{fill}" stroke="{STROKE}" stroke-width="{STROKE_WIDTH}"/>'
        )
    else:
        d = (f"M {_fmt(x)} {_fmt(y - half)} L {_fmt(x + half)} {_fmt(y)} "
             f"L {_fmt(x)} {_fmt(y + half)} L {_fmt(x - half)} {_fmt(y)} Z")
        parts.append(
            f'<path d="{d}" fill="{fill}" stroke="{STROKE}" '
            f'stroke-width="{STROKE_WIDTH}" stroke-linejoin="round"/>'
        )

    if node.status == "carrier":
        parts.append(f'<circle cx="{_fmt(x)}" cy="{_fmt(y)}" r="5" fill="{STROKE}"/>')
    elif node.status == "unknown":
        parts.append(
            f'<text x="{_fmt(x)}" y="{_fmt(y)}" text-anchor="middle" '
            f'dominant-baseline="central" font-size="{_fmt(NAME_FONT + 3)}" '
            f'font-weight="700" fill="{STROKE if not affected else PAPER}">?</text>'
        )

    if node.deceased:
        # Standard notation: a single diagonal through the symbol, drawn in the
        # contrasting colour so it stays visible on a filled (affected) shape.
        reach = half + 7
        parts.append(
            f'<line x1="{_fmt(x - reach)}" y1="{_fmt(y + reach)}" '
            f'x2="{_fmt(x + reach)}" y2="{_fmt(y - reach)}" '
            f'stroke="{PAPER if affected else STROKE}" stroke-width="{STROKE_WIDTH}" '
            f'stroke-linecap="round"/>'
        )

    if node.proband:
        # Arrow into the lower-left corner, with the conventional "P".
        tail_x, tail_y = x - half - 20, y + half + 18
        head_x, head_y = x - half - 3, y + half + 1
        parts.append(
            f'<line x1="{_fmt(tail_x)}" y1="{_fmt(tail_y)}" '
            f'x2="{_fmt(head_x)}" y2="{_fmt(head_y)}" stroke="{ACCENT}" '
            f'stroke-width="{STROKE_WIDTH}" marker-end="url(#vm-arrow)"/>'
        )
        parts.append(
            f'<text x="{_fmt(tail_x - 3)}" y="{_fmt(tail_y + 4)}" text-anchor="end" '
            f'font-size="{_fmt(AGE_FONT)}" font-weight="700" fill="{ACCENT}">P</text>'
        )
    return parts


def _label(node: NodeBox) -> List[str]:
    parts: List[str] = []
    cx = node.label_centre
    y = node.label_top + NAME_FONT
    for line in node.label_lines:
        parts.append(
            f'<text x="{_fmt(cx)}" y="{_fmt(y)}" text-anchor="middle" '
            f'font-size="{_fmt(NAME_FONT)}" font-weight="600" fill="{TEXT}">'
            f'{escape(line)}</text>'
        )
        y += LINE_HEIGHT
    if node.age is not None:
        parts.append(
            f'<text x="{_fmt(cx)}" y="{_fmt(y)}" text-anchor="middle" '
            f'font-size="{_fmt(AGE_FONT)}" fill="{MUTED}">{escape(str(node.age))}y</text>'
        )
    return parts


def _connector(segment: Segment) -> List[str]:
    points = " ".join(f"{_fmt(px)},{_fmt(py)}" for px, py in segment.points)
    base = (f'<polyline points="{points}" fill="none" stroke="{LINE}" '
            f'stroke-width="{CONNECTOR_WIDTH}" stroke-linecap="square" '
            f'stroke-linejoin="miter"/>')
    if segment.kind != "consanguineous":
        return [base]

    # Consanguinity is drawn as a double bar.
    (x1, y1), (x2, y2) = segment.points[0], segment.points[-1]
    return [
        f'<line x1="{_fmt(x1)}" y1="{_fmt(y1 - 3)}" x2="{_fmt(x2)}" y2="{_fmt(y2 - 3)}" '
        f'stroke="{LINE}" stroke-width="{CONNECTOR_WIDTH}"/>',
        f'<line x1="{_fmt(x1)}" y1="{_fmt(y1 + 3)}" x2="{_fmt(x2)}" y2="{_fmt(y2 + 3)}" '
        f'stroke="{LINE}" stroke-width="{CONNECTOR_WIDTH}"/>',
    ]


LEGEND_ENTRIES = [
    ("male", "unaffected", False, "Male"),
    ("female", "unaffected", False, "Female"),
    ("unknown", "unaffected", False, "Unknown sex"),
    ("male", "affected", False, "Affected"),
    ("female", "carrier", False, "Carrier"),
    ("male", "unaffected", True, "Deceased"),
]
LEGEND_SWATCH = 15.0
LEGEND_ROW_HEIGHT = 25.0
LEGEND_MARGIN = 26.0


def _legend_entry_widths() -> List[float]:
    return [LEGEND_SWATCH + 7 + text_width(label, AGE_FONT) + 20
            for *_, label in LEGEND_ENTRIES]


def _legend_rows(canvas_width: float) -> List[List[int]]:
    """Pack legend entries into rows that fit the canvas, so nothing is clipped."""
    widths = _legend_entry_widths()
    available = max(canvas_width - LEGEND_MARGIN * 2, widths[0])
    rows: List[List[int]] = []
    current: List[int] = []
    used = 0.0
    for index, width in enumerate(widths):
        if current and used + width > available:
            rows.append(current)
            current, used = [], 0.0
        current.append(index)
        used += width
    if current:
        rows.append(current)
    return rows


def legend_height(canvas_width: float) -> float:
    return 20.0 + len(_legend_rows(canvas_width)) * LEGEND_ROW_HEIGHT + 12.0


def _legend(canvas_width: float, top: float) -> List[str]:
    """Key strip along the bottom, so the notation is self-explanatory."""
    widths = _legend_entry_widths()
    rows = _legend_rows(canvas_width)
    size = LEGEND_SWATCH

    parts = [
        f'<line x1="{_fmt(LEGEND_MARGIN)}" y1="{_fmt(top)}" '
        f'x2="{_fmt(canvas_width - LEGEND_MARGIN)}" y2="{_fmt(top)}" '
        f'stroke="#e5e7eb" stroke-width="1"/>'
    ]

    for row_index, row in enumerate(rows):
        row_width = sum(widths[i] for i in row)
        x = max(LEGEND_MARGIN, (canvas_width - row_width) / 2)
        y = top + 20 + row_index * LEGEND_ROW_HEIGHT

        for entry_index in row:
            gender, status, deceased, label = LEGEND_ENTRIES[entry_index]
            cx, cy = x + size / 2, y
            half = size / 2
            fill = STROKE if status == "affected" else PAPER
            if gender == "male":
                parts.append(f'<rect x="{_fmt(cx - half)}" y="{_fmt(cy - half)}" '
                             f'width="{_fmt(size)}" height="{_fmt(size)}" fill="{fill}" '
                             f'stroke="{STROKE}" stroke-width="1.5"/>')
            elif gender == "female":
                parts.append(f'<circle cx="{_fmt(cx)}" cy="{_fmt(cy)}" r="{_fmt(half)}" '
                             f'fill="{fill}" stroke="{STROKE}" stroke-width="1.5"/>')
            else:
                d = (f"M {_fmt(cx)} {_fmt(cy - half)} L {_fmt(cx + half)} {_fmt(cy)} "
                     f"L {_fmt(cx)} {_fmt(cy + half)} L {_fmt(cx - half)} {_fmt(cy)} Z")
                parts.append(f'<path d="{d}" fill="{fill}" stroke="{STROKE}" stroke-width="1.5"/>')

            if status == "carrier":
                parts.append(f'<circle cx="{_fmt(cx)}" cy="{_fmt(cy)}" r="2.6" fill="{STROKE}"/>')
            if deceased:
                reach = half + 3
                parts.append(f'<line x1="{_fmt(cx - reach)}" y1="{_fmt(cy + reach)}" '
                             f'x2="{_fmt(cx + reach)}" y2="{_fmt(cy - reach)}" '
                             f'stroke="{STROKE}" stroke-width="1.5"/>')

            parts.append(f'<text x="{_fmt(x + size + 7)}" y="{_fmt(cy + 4)}" '
                         f'font-size="{_fmt(AGE_FONT)}" fill="{MUTED}">{escape(label)}</text>')
            x += widths[entry_index]
    return parts


def render_svg(layout: PedigreeLayout, title: str = "Pedigree chart",
               show_legend: bool = True) -> str:
    """Render a resolved layout to a standalone SVG document.

    Narrow charts are widened just enough to keep the legend on one or two rows;
    the chart itself stays centred in whatever width results.
    """
    canvas_width = layout.width
    if show_legend:
        natural = sum(_legend_entry_widths()) + LEGEND_MARGIN * 2
        canvas_width = max(layout.width, min(natural, 640.0))

    band = legend_height(canvas_width) if show_legend else 0.0
    height = layout.height + band
    offset = (canvas_width - layout.width) / 2

    out: List[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'viewBox="0 0 {_fmt(canvas_width)} {_fmt(height)}" '
        f'width="{_fmt(canvas_width)}" height="{_fmt(height)}" '
        f'role="img" aria-label="{escape(title)}" '
        f'font-family="Inter, Segoe UI, Helvetica, Arial, sans-serif">',
        f'<title>{escape(title)}</title>',
        '<defs>'
        f'<marker id="vm-arrow" viewBox="0 0 10 10" refX="9" refY="5" '
        f'markerWidth="5" markerHeight="5" orient="auto-start-reverse">'
        f'<path d="M 0 0 L 10 5 L 0 10 z" fill="{ACCENT}"/></marker>'
        '</defs>',
        f'<rect width="100%" height="100%" fill="{PAPER}"/>',
        f'<g transform="translate({_fmt(offset)},0)">',
    ]

    # Connectors first so symbols always sit on top of the lines.
    out.append('<g class="connectors">')
    for segment in layout.segments:
        out.extend(_connector(segment))
    out.append("</g>")

    out.append('<g class="individuals">')
    for node in layout.nodes:
        out.extend(_symbol(node))
        out.extend(_label(node))
    out.append("</g>")
    out.append("</g>")

    if show_legend:
        out.append('<g class="legend">')
        out.extend(_legend(canvas_width, layout.height))
        out.append("</g>")

    out.append("</svg>")
    return "".join(out)


def render_pedigree_svg(individuals, relationships, title: str = "Pedigree chart",
                        trace=None, show_legend: bool = True) -> str:
    """Convenience one-shot: raw family graph in, SVG string out."""
    from analysis.pedigree_layout import compute_layout
    layout = compute_layout(individuals, relationships, trace=trace)
    return render_svg(layout, title=title, show_legend=show_legend)
