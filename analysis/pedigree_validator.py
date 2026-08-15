"""
Geometric validator for a resolved pedigree layout.

Checks the geometry directly rather than inspecting a rendered image, so it is
fast, exact and gives a precise reason for every failure. This is what makes the
render loop self-verifying: if the validator is clean, the chart is correct.

Every connector produced by the layout engine is axis-aligned, so intersection
tests reduce to interval overlaps.

Severities
----------
``error``    a defect a clinician would call wrong — overlapping symbols, a line
             drawn through a shape or a label, a broken generation relationship.
``warning``  legible but not ideal — crossing connectors, disconnected branches.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

from analysis.pedigree_layout import PedigreeLayout, NodeBox, Segment

EPS = 0.75          # tolerance for "touching is fine, overlapping is not"
ALIGN_TOL = 2.5     # how far a child's centre may sit off its parents' descent line


@dataclass
class Issue:
    code: str
    severity: str
    message: str
    details: Dict[str, Any] = field(default_factory=dict)

    def __str__(self) -> str:
        return f"[{self.severity.upper()}] {self.code}: {self.message}"


@dataclass
class ValidationReport:
    issues: List[Issue] = field(default_factory=list)
    stats: Dict[str, Any] = field(default_factory=dict)

    @property
    def errors(self) -> List[Issue]:
        return [i for i in self.issues if i.severity == "error"]

    @property
    def warnings(self) -> List[Issue]:
        return [i for i in self.issues if i.severity == "warning"]

    @property
    def ok(self) -> bool:
        return not self.errors

    def add(self, code: str, severity: str, message: str, **details: Any) -> None:
        self.issues.append(Issue(code, severity, message, details))

    def summary(self) -> str:
        if self.ok and not self.warnings:
            return "clean"
        return f"{len(self.errors)} error(s), {len(self.warnings)} warning(s)"


# ── geometry helpers ───────────────────────────────────────────────────────

Rect = Tuple[float, float, float, float]


def _overlap(a0: float, a1: float, b0: float, b1: float, eps: float = EPS) -> bool:
    """True when two 1-D intervals share more than ``eps`` of length."""
    lo = max(min(a0, a1), min(b0, b1))
    hi = min(max(a0, a1), max(b0, b1))
    return (hi - lo) > eps


def _rects_overlap(a: Rect, b: Rect, eps: float = EPS) -> bool:
    return _overlap(a[0], a[2], b[0], b[2], eps) and _overlap(a[1], a[3], b[1], b[3], eps)


def _symbol_rect(node: NodeBox) -> Rect:
    return (node.left, node.top, node.right, node.bottom)


def _label_rect(node: NodeBox) -> Rect:
    return node.label_rect()


def _sub_segments(segment: Segment) -> List[Tuple[float, float, float, float]]:
    return [(segment.points[i][0], segment.points[i][1],
             segment.points[i + 1][0], segment.points[i + 1][1])
            for i in range(len(segment.points) - 1)]


def _segment_hits_rect(x1: float, y1: float, x2: float, y2: float,
                       rect: Rect, eps: float = EPS) -> bool:
    """Does an axis-aligned segment pass through a rectangle's interior?

    Endpoints landing on the boundary are fine — that is how connectors attach.
    """
    rx0, ry0, rx1, ry1 = rect
    if abs(x1 - x2) < EPS:                                   # vertical
        return (rx0 + eps) < x1 < (rx1 - eps) and _overlap(y1, y2, ry0, ry1, eps)
    if abs(y1 - y2) < EPS:                                   # horizontal
        return (ry0 + eps) < y1 < (ry1 - eps) and _overlap(x1, x2, rx0, rx1, eps)

    # Diagonals are not produced by the router; treat as a bounding-box test.
    return _rects_overlap((min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2)), rect, eps)


def _segments_cross(a: Tuple[float, float, float, float],
                    b: Tuple[float, float, float, float]) -> bool:
    """True for a genuine perpendicular crossing (T-junctions do not count)."""
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    a_vert, b_vert = abs(ax1 - ax2) < EPS, abs(bx1 - bx2) < EPS
    if a_vert == b_vert:
        return False
    if b_vert:
        ax1, ay1, ax2, ay2, bx1, by1, bx2, by2 = bx1, by1, bx2, by2, ax1, ay1, ax2, ay2
    # a is now vertical, b horizontal
    return (min(by1, by2) + EPS < ay1 or True) and \
        (min(ay1, ay2) + EPS < by1 < max(ay1, ay2) - EPS) and \
        (min(bx1, bx2) + EPS < ax1 < max(bx1, bx2) - EPS)


# ── checks ─────────────────────────────────────────────────────────────────

def validate_layout(layout: PedigreeLayout,
                    individuals: Optional[Sequence[Dict[str, Any]]] = None,
                    relationships: Optional[Sequence[Dict[str, Any]]] = None
                    ) -> ValidationReport:
    """Run every geometric and structural check against a resolved layout."""
    report = ValidationReport()
    nodes = layout.nodes
    by_id = {n.id: n for n in nodes}

    if not nodes:
        report.add("empty", "error", "Layout contains no individuals")
        return report

    # 1. Symbols must never overlap.
    for i, a in enumerate(nodes):
        for b in nodes[i + 1:]:
            if _rects_overlap(_symbol_rect(a), _symbol_rect(b)):
                report.add("symbol_overlap", "error",
                           f"Symbols for '{a.id}' and '{b.id}' overlap",
                           a=a.id, b=b.id,
                           a_box=_symbol_rect(a), b_box=_symbol_rect(b))

    # 2. Labels must never overlap another label or another symbol.
    for i, a in enumerate(nodes):
        for b in nodes[i + 1:]:
            if _rects_overlap(_label_rect(a), _label_rect(b)):
                report.add("label_overlap", "error",
                           f"Name labels for '{a.id}' and '{b.id}' overlap",
                           a=a.id, b=b.id)
        for b in nodes:
            if a.id != b.id and _rects_overlap(_label_rect(a), _symbol_rect(b)):
                report.add("label_symbol_overlap", "error",
                           f"Label for '{a.id}' overlaps the symbol for '{b.id}'",
                           label=a.id, symbol=b.id)

    # 3. Connectors must not be drawn through a symbol or a label.
    for segment in layout.segments:
        for x1, y1, x2, y2 in _sub_segments(segment):
            for node in nodes:
                if _segment_hits_rect(x1, y1, x2, y2, _symbol_rect(node)):
                    report.add("line_through_symbol", "error",
                               f"A {segment.kind} connector is drawn through "
                               f"the symbol for '{node.id}'",
                               kind=segment.kind, node=node.id,
                               segment=[x1, y1, x2, y2], box=_symbol_rect(node))
                if _segment_hits_rect(x1, y1, x2, y2, _label_rect(node)):
                    report.add("line_through_label", "error",
                               f"A {segment.kind} connector crosses the name "
                               f"label for '{node.id}'",
                               kind=segment.kind, node=node.id,
                               segment=[x1, y1, x2, y2])

    # 4. Duplicate/overlapping collinear connectors read as one thick smudge.
    flat: List[Tuple[str, Tuple[float, float, float, float]]] = [
        (s.kind, sub) for s in layout.segments for sub in _sub_segments(s)
    ]
    for i, (kind_a, a) in enumerate(flat):
        for kind_b, b in flat[i + 1:]:
            a_vert, b_vert = abs(a[0] - a[2]) < EPS, abs(b[0] - b[2]) < EPS
            if a_vert != b_vert:
                continue
            if a_vert and abs(a[0] - b[0]) < EPS and _overlap(a[1], a[3], b[1], b[3], 2.0):
                report.add("duplicate_connector", "error",
                           "Two vertical connectors are drawn on top of each other",
                           kinds=[kind_a, kind_b], a=list(a), b=list(b))
            elif not a_vert and abs(a[1] - b[1]) < EPS and _overlap(a[0], a[2], b[0], b[2], 2.0):
                report.add("duplicate_connector", "error",
                           "Two horizontal connectors are drawn on top of each other",
                           kinds=[kind_a, kind_b], a=list(a), b=list(b))

    # 5. Everything must sit inside the canvas.
    for node in nodes:
        x0, y0, x1, y1 = node.bounds()
        if x0 < 0 or y0 < 0 or x1 > layout.width or y1 > layout.height:
            report.add("out_of_canvas", "error",
                       f"'{node.id}' falls outside the {layout.width:.0f}×"
                       f"{layout.height:.0f} canvas",
                       node=node.id, bounds=[x0, y0, x1, y1])

    # 6. ...and the canvas must not be mostly empty.
    xs = [b for n in nodes for b in (n.bounds()[0], n.bounds()[2])]
    ys = [b for n in nodes for b in (n.bounds()[1], n.bounds()[3])]
    used = (max(xs) - min(xs)) * (max(ys) - min(ys))
    canvas = layout.width * layout.height
    fill_ratio = used / canvas if canvas else 0.0
    report.stats["fill_ratio"] = round(fill_ratio, 3)
    if canvas and fill_ratio < 0.45:
        report.add("wasted_canvas", "warning",
                   f"Content occupies only {fill_ratio:.0%} of the canvas",
                   fill_ratio=fill_ratio)

    # 7. A pedigree has exactly one index case, so at most one arrow.
    probands = [n.id for n in nodes if n.proband]
    if len(probands) > 1:
        report.add("multiple_probands", "error",
                   f"{len(probands)} individuals are marked as the proband",
                   ids=probands)
    report.stats["proband"] = probands[0] if probands else None

    # 8. Structural checks against the source graph.
    if individuals is not None and relationships is not None:
        _check_structure(layout, by_id, individuals, relationships, report)

    # 8. Crossing connectors — legible, but worth counting.
    crossings = 0
    for i, (_, a) in enumerate(flat):
        for _, b in flat[i + 1:]:
            if _segments_cross(a, b):
                crossings += 1
    report.stats["crossings"] = crossings
    if crossings:
        report.add("connector_crossings", "warning",
                   f"{crossings} connector crossing(s) in the drawing",
                   count=crossings)

    report.stats.update({
        "nodes": len(nodes),
        "segments": len(layout.segments),
        "canvas": [layout.width, layout.height],
        "generations": len(layout.generations),
    })
    return report


def _check_structure(layout: PedigreeLayout, by_id: Dict[str, NodeBox],
                     individuals: Sequence[Dict[str, Any]],
                     relationships: Sequence[Dict[str, Any]],
                     report: ValidationReport) -> None:
    """Generation relationships, couple adjacency, and child centring."""
    from analysis.pedigree_layout import FamilyGraph
    from analysis.pedigree_logging import null_trace

    graph = FamilyGraph(individuals, relationships, null_trace())

    missing = [p["id"] for p in graph.people.values() if p["id"] not in by_id]
    if missing:
        report.add("missing_nodes", "error",
                   f"{len(missing)} individual(s) were dropped from the layout",
                   ids=missing)

    for pid in graph.order:
        if pid not in by_id:
            continue
        node = by_id[pid]

        for child in graph.children[pid]:
            if child not in by_id:
                continue
            delta = by_id[child].generation - node.generation
            if delta != 1:
                report.add("generation_error", "error",
                           f"'{child}' should be exactly one generation below "
                           f"its parent '{pid}' (got {delta})",
                           parent=pid, child=child, delta=delta)

        for spouse in graph.spouses[pid]:
            if spouse in by_id and by_id[spouse].generation != node.generation:
                report.add("generation_error", "error",
                           f"Spouses '{pid}' and '{spouse}' are on different rows",
                           a=pid, b=spouse)

        for sibling in graph.siblings[pid]:
            if sibling in by_id and by_id[sibling].generation != node.generation:
                report.add("generation_error", "error",
                           f"Siblings '{pid}' and '{sibling}' are on different rows",
                           a=pid, b=sibling)

    # Couples must be horizontally adjacent — nobody drawn between them.
    seen: set = set()
    for pid in graph.order:
        for spouse in graph.spouses[pid]:
            pair = tuple(sorted((pid, spouse)))
            if pair in seen or pid not in by_id or spouse not in by_id:
                continue
            seen.add(pair)
            a, b = by_id[pair[0]], by_id[pair[1]]
            if a.generation != b.generation:
                continue
            lo, hi = min(a.x, b.x), max(a.x, b.x)
            intruders = [n.id for n in layout.nodes
                         if n.generation == a.generation and n.id not in pair
                         and lo < n.x < hi]
            if intruders:
                report.add("couple_split", "error",
                           f"'{intruders[0]}' is drawn between the couple "
                           f"'{pair[0]}' and '{pair[1]}'",
                           couple=list(pair), between=intruders)

    # Children should hang under the middle of their parents.
    for parents, kids in graph.unions():
        present_parents = [p for p in parents if p in by_id]
        present_kids = [k for k in kids if k in by_id]
        if not present_parents or not present_kids:
            continue
        pxs = sorted(by_id[p].x for p in present_parents)
        descent_x = (pxs[0] + pxs[-1]) / 2
        kxs = [by_id[k].x for k in present_kids]
        if not (min(kxs) - ALIGN_TOL <= descent_x <= max(kxs) + ALIGN_TOL):
            report.add("children_off_centre", "warning",
                       f"Children of {list(present_parents)} are not centred "
                       f"under their parents",
                       parents=list(present_parents), descent_x=round(descent_x, 1),
                       child_span=[round(min(kxs), 1), round(max(kxs), 1)])

    components = graph.components()
    if len(components) > 1:
        report.add("disconnected", "warning",
                   f"Pedigree splits into {len(components)} disconnected groups",
                   components=[c[:8] for c in components])


def format_report(report: ValidationReport, name: str = "") -> str:
    """Human-readable report for console output."""
    header = f"{name}: {report.summary()}" if name else report.summary()
    lines = [header]
    for issue in report.errors + report.warnings:
        lines.append(f"    {issue}")
        if issue.details:
            compact = {k: v for k, v in issue.details.items()
                       if k in ("a", "b", "node", "child", "parent", "ids",
                                "count", "kinds", "between", "couple")}
            if compact:
                lines.append(f"        {compact}")
    return "\n".join(lines)
