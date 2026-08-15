"""
Pedigree layout engine.

Turns an ``{individuals, relationships}`` graph into fully-resolved geometry:
node boxes, label boxes and orthogonal connector polylines, on a canvas sized to
its content. Rendering is a separate concern (see ``pedigree_svg``), and the
geometry produced here is what the automated validator checks — so correctness
is machine-verifiable without ever looking at an image.

Pipeline
--------
1. ``build_graph``      normalise relationships; derive marriages from shared
                        children and sibling links from shared parents.
2. ``solve_generations`` BFS over *every* connected component (a single-seed BFS
                        was the bug that made disconnected relatives float up a
                        row), then anchor components relative to one another.
3. ``build_blocks``     group spouses into rigid blocks so couples never split.
4. ``order_blocks``     median/barycenter crossing reduction, generation by
                        generation.
5. ``assign_x``         alternating up/down barycenter passes, each followed by
                        an exact isotonic (pool-adjacent-violators) separation
                        solve that enforces minimum gaps while minimising
                        displacement.
6. ``route_edges``      marriage bars, descent lines and shared sibship buses,
                        with bus levels coloured so buses never sit on top of
                        each other.
"""

import math
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

from analysis.pedigree_logging import PedigreeTrace, null_trace

# ── geometry constants ─────────────────────────────────────────────────────

SYMBOL = 42.0              # symbol width/height
ROW_SPACING = 185.0        # vertical distance between generation centres
MIN_GAP = 34.0             # minimum clear space between two node label boxes
COUPLE_GAP = 78.0          # preferred centre-to-centre distance within a couple
PADDING = 60.0             # canvas margin around content

NAME_FONT = 13.0
AGE_FONT = 11.0
LINE_HEIGHT = 15.0
LABEL_TOP_PAD = 9.0        # gap between symbol bottom and first label line
MAX_LABEL_WIDTH = 96.0     # names wrap to stay within this
MAX_NAME_LINES = 3
LABEL_CLEARANCE = 9.0      # clear space a connector keeps from any label
PROBAND_ARROW_REACH = 36.0  # room the proband arrow needs left of the symbol

CHAR_RATIO = 0.58          # average glyph width as a fraction of font size


def text_width(text: str, font_size: float) -> float:
    """Approximate rendered width of a string. Deliberately slightly generous —
    over-estimating pushes nodes apart, which is the safe direction."""
    wide = sum(1 for c in text if c in "MW@mw")
    narrow = sum(1 for c in text if c in "iljtfrI.,:;'\" ")
    normal = len(text) - wide - narrow
    return font_size * (normal * CHAR_RATIO + wide * 0.88 + narrow * 0.32)


def wrap_label(name: str, font_size: float = NAME_FONT,
               max_width: float = MAX_LABEL_WIDTH,
               max_lines: int = MAX_NAME_LINES) -> List[str]:
    """Greedy word wrap, breaking over-long single words by character."""
    words = str(name).split()
    if not words:
        return [""]

    lines: List[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if current and text_width(candidate, font_size) > max_width:
            lines.append(current)
            current = word
        else:
            current = candidate

        # A single word wider than the box has to be split mid-word.
        while text_width(current, font_size) > max_width and len(current) > 1:
            cut = len(current)
            while cut > 1 and text_width(current[:cut], font_size) > max_width:
                cut -= 1
            lines.append(current[:cut])
            current = current[cut:]

    if current:
        lines.append(current)

    if len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] = lines[-1][:-1] + "…" if len(lines[-1]) > 1 else "…"
    return lines


# ── output structures ──────────────────────────────────────────────────────

@dataclass
class NodeBox:
    """A laid-out individual: symbol geometry plus its label block."""
    id: str
    name: str
    gender: str
    status: str
    deceased: bool
    proband: bool
    generation: int
    age: Optional[int]
    conditions: List[str]
    x: float = 0.0             # symbol centre
    y: float = 0.0
    size: float = SYMBOL
    label_lines: List[str] = field(default_factory=list)
    label_width: float = 0.0
    # Horizontal nudge applied to the label block. Non-zero only for a parent
    # whose descent line would otherwise be drawn straight through their own
    # name — the space for the shift is reserved during spacing.
    label_dx: float = 0.0

    # -- symbol bounds --
    @property
    def left(self) -> float: return self.x - self.size / 2
    @property
    def right(self) -> float: return self.x + self.size / 2
    @property
    def top(self) -> float: return self.y - self.size / 2
    @property
    def bottom(self) -> float: return self.y + self.size / 2

    @property
    def label_height(self) -> float:
        h = len(self.label_lines) * LINE_HEIGHT
        if self.age is not None:
            h += LINE_HEIGHT
        return h

    @property
    def label_top(self) -> float:
        return self.bottom + LABEL_TOP_PAD

    @property
    def label_bottom(self) -> float:
        return self.label_top + self.label_height

    @property
    def label_centre(self) -> float:
        return self.x + self.label_dx

    def label_rect(self) -> Tuple[float, float, float, float]:
        half = self.label_width / 2
        return (self.label_centre - half, self.label_top,
                self.label_centre + half, self.label_bottom)

    def bounds(self) -> Tuple[float, float, float, float]:
        """Full footprint (symbol + label) as (x0, y0, x1, y1)."""
        lx0, _, lx1, _ = self.label_rect()
        return (min(self.left, lx0), self.top, max(self.right, lx1), self.label_bottom)

    def extents(self) -> Tuple[float, float]:
        """Distance from the symbol centre to the left and right edges of the
        node's footprint. Asymmetric once a label has been nudged."""
        x0, _, x1, _ = self.bounds()
        return (self.x - x0, x1 - self.x)


@dataclass
class Segment:
    """An orthogonal connector polyline."""
    kind: str                     # marriage | consanguineous | descent | sibship | drop
    points: List[Tuple[float, float]]
    meta: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PedigreeLayout:
    width: float
    height: float
    nodes: List[NodeBox]
    segments: List[Segment]
    generations: Dict[int, List[str]]
    warnings: List[str] = field(default_factory=list)

    def node(self, node_id: str) -> Optional[NodeBox]:
        return next((n for n in self.nodes if n.id == node_id), None)


# ── graph ──────────────────────────────────────────────────────────────────

class FamilyGraph:
    """Normalised view of the pedigree relationships."""

    def __init__(self, individuals: Sequence[Dict[str, Any]],
                 relationships: Sequence[Dict[str, Any]],
                 trace: Optional[PedigreeTrace] = None):
        self.trace = trace or null_trace()
        self.order: List[str] = []
        self.people: Dict[str, Dict[str, Any]] = {}

        for index, raw in enumerate(individuals):
            person = self._normalise_person(raw, index)
            pid = person["id"]
            if pid in self.people:
                self.trace.warn("graph", f"Duplicate individual id '{pid}' — merging")
                self.people[pid].update({k: v for k, v in person.items() if v not in (None, "", [])})
                continue
            self.people[pid] = person
            self.order.append(pid)

        self.parents: Dict[str, List[str]] = {pid: [] for pid in self.order}
        self.children: Dict[str, List[str]] = {pid: [] for pid in self.order}
        self.spouses: Dict[str, List[str]] = {pid: [] for pid in self.order}
        self.siblings: Dict[str, Set[str]] = {pid: set() for pid in self.order}

        dropped = 0
        for rel in relationships:
            rtype = str(self._get(rel, "type", "")).strip().lower()
            p1 = str(self._get(rel, "person1", "")).strip()
            p2 = str(self._get(rel, "person2", "")).strip()
            if p1 not in self.people or p2 not in self.people or p1 == p2:
                dropped += 1
                continue

            if rtype == "parent-child":
                if p2 not in self.children[p1]:
                    self.children[p1].append(p2)
                if p1 not in self.parents[p2]:
                    self.parents[p2].append(p1)
            elif rtype == "marriage":
                if p2 not in self.spouses[p1]:
                    self.spouses[p1].append(p2)
                if p1 not in self.spouses[p2]:
                    self.spouses[p2].append(p1)
            elif rtype == "sibling":
                self.siblings[p1].add(p2)
                self.siblings[p2].add(p1)
            else:
                dropped += 1

        if dropped:
            self.trace.warn("graph", f"Dropped {dropped} relationship(s) with unknown type or dangling ids")

        self._derive_implicit_links()
        self._elect_proband()

        self.trace.event("graph", "Family graph built", {
            "individuals": len(self.order),
            "parent_child": sum(len(v) for v in self.children.values()),
            "marriages": sum(len(v) for v in self.spouses.values()) // 2,
            "sibling_links": sum(len(v) for v in self.siblings.values()) // 2,
        })

    @staticmethod
    def _get(obj: Any, key: str, default: Any = None) -> Any:
        if isinstance(obj, dict):
            return obj.get(key, default)
        if hasattr(obj, "get"):
            try:
                return obj.get(key, default)
            except Exception:
                pass
        return getattr(obj, key, default)

    def _normalise_person(self, raw: Any, index: int) -> Dict[str, Any]:
        pid = str(self._get(raw, "id", "") or "").strip()
        name = str(self._get(raw, "name", "") or "").strip()
        if not pid:
            pid = re.sub(r"\W+", "_", name.lower()) or f"person_{index + 1}"
        if not name:
            name = pid.replace("_", " ").title()

        gender = str(self._get(raw, "gender", "unknown") or "unknown").strip().lower()
        gender = {"m": "male", "f": "female"}.get(gender, gender)
        if gender not in ("male", "female", "unknown"):
            gender = "unknown"
        if gender == "unknown":
            gender = self._infer_gender(f"{name} {pid}".lower())

        status = str(self._get(raw, "status", "unaffected") or "unaffected").strip().lower()
        if status not in ("unaffected", "affected", "carrier", "unknown", "deceased"):
            status = "unaffected"

        deceased = bool(self._get(raw, "deceased", False)) or status == "deceased"
        if status == "deceased":
            # 'deceased' is a life-status, not a disease status; keep them separate
            # so a dead person can still be drawn as affected/unaffected/unknown.
            status = "unknown"

        age = self._get(raw, "age", None)
        try:
            age = int(age) if age is not None and str(age).strip() != "" else None
        except (TypeError, ValueError):
            age = None

        conditions = self._get(raw, "conditions", []) or []
        if not isinstance(conditions, list):
            conditions = [str(conditions)]

        return {
            "id": pid, "name": name, "gender": gender, "status": status,
            "deceased": deceased, "age": age,
            "conditions": [str(c) for c in conditions],
            "proband": bool(self._get(raw, "proband", False)),
        }

    def _elect_proband(self) -> None:
        """Mark exactly one individual as the proband.

        A pedigree has a single index case, so the arrow must land on one
        symbol. Names are matched on whole words — a plain substring test puts
        the arrow on "Proband's Father" and "Proband's Cousin" too.
        """
        word = re.compile(r"\b(proband|patient|index case)\b")

        def score(person: Dict[str, Any]) -> Tuple[int, int]:
            name, pid = person["name"].lower(), person["id"].lower()
            if person["proband"]:
                return (3, -len(name))
            if name in ("proband", "patient") or pid in ("proband", "patient"):
                return (2, -len(name))
            if word.search(name) or word.search(pid.replace("_", " ")):
                return (1, -len(name))
            return (0, 0)

        ranked = sorted(self.people.values(), key=score, reverse=True)
        for person in self.people.values():
            person["proband"] = False
        if ranked and score(ranked[0])[0] > 0:
            ranked[0]["proband"] = True
            self.trace.event("graph", f"Proband identified: '{ranked[0]['id']}'")
        else:
            self.trace.event("graph", "No proband identified; no arrow drawn")

    @staticmethod
    def _infer_gender(blob: str) -> str:
        male = ("father", "dad", "son", "brother", "grandfather", "grandpa",
                "uncle", "husband", "nephew", "male", "boy", "papa")
        female = ("mother", "mom", "daughter", "sister", "grandmother", "grandma",
                  "aunt", "wife", "niece", "female", "girl", "mama")
        if any(w in blob for w in male):
            return "male"
        if any(w in blob for w in female):
            return "female"
        return "unknown"

    def _derive_implicit_links(self) -> None:
        """Fill in edges the model left out.

        Co-parents of the same child are a couple, and people sharing a parent
        are siblings. Both are implied by the data, and having them explicit
        keeps the generation solver and the block builder from having to guess.
        """
        derived_marriages = 0
        by_child: Dict[str, List[str]] = {}
        for parent, kids in self.children.items():
            for kid in kids:
                by_child.setdefault(kid, []).append(parent)

        for kid, parents in by_child.items():
            if len(parents) == 2:
                a, b = parents
                if b not in self.spouses[a]:
                    self.spouses[a].append(b)
                    self.spouses[b].append(a)
                    derived_marriages += 1
            elif len(parents) > 2:
                self.trace.warn("graph", f"'{kid}' has {len(parents)} parents; using the first two",
                                {"parents": parents})

        derived_siblings = 0
        for parent, kids in self.children.items():
            for i, a in enumerate(kids):
                for b in kids[i + 1:]:
                    if b not in self.siblings[a]:
                        self.siblings[a].add(b)
                        self.siblings[b].add(a)
                        derived_siblings += 1

        if derived_marriages or derived_siblings:
            self.trace.event("graph", "Derived implicit relationships", {
                "marriages_from_shared_children": derived_marriages,
                "sibling_links_from_shared_parents": derived_siblings,
            })

    # -- queries --

    def components(self) -> List[List[str]]:
        """Connected components over all relationship types."""
        seen: Set[str] = set()
        out: List[List[str]] = []
        for pid in self.order:
            if pid in seen:
                continue
            stack, comp = [pid], []
            seen.add(pid)
            while stack:
                cur = stack.pop()
                comp.append(cur)
                neighbours = (self.parents[cur] + self.children[cur] +
                              self.spouses[cur] + list(self.siblings[cur]))
                for nxt in neighbours:
                    if nxt not in seen:
                        seen.add(nxt)
                        stack.append(nxt)
            out.append(sorted(comp, key=self.order.index))
        return out

    def unions(self) -> List[Tuple[Tuple[str, ...], List[str]]]:
        """Parent-set → children, one entry per reproductive union."""
        by_parents: Dict[Tuple[str, ...], List[str]] = {}
        for pid in self.order:
            parents = tuple(sorted(self.parents[pid]))
            if parents:
                by_parents.setdefault(parents, []).append(pid)
        return list(by_parents.items())

    def ancestors(self, pid: str, depth: int = 12) -> Set[str]:
        out: Set[str] = set()
        frontier = [(pid, 0)]
        while frontier:
            cur, d = frontier.pop()
            if d >= depth:
                continue
            for parent in self.parents.get(cur, []):
                if parent not in out:
                    out.add(parent)
                    frontier.append((parent, d + 1))
        return out


# ── generation solving ─────────────────────────────────────────────────────

# Used only to anchor components that share no edges. Structural constraints
# always win inside a component; these hints just stop an unconnected aunt from
# floating into the grandparents' row.
ROLE_DEPTH_HINTS: List[Tuple[Tuple[str, ...], int]] = [
    (("great grandfather", "great grandmother", "great-grand"), 0),
    (("grandfather", "grandmother", "grandpa", "grandma", "grandparent"), 1),
    (("father", "mother", "aunt", "uncle", "dad", "mom", "parent"), 2),
    (("proband", "patient", "sibling", "brother", "sister", "cousin", "self"), 3),
    (("son", "daughter", "child", "niece", "nephew", "grandchild"), 4),
]


def _role_hint(person: Dict[str, Any]) -> Optional[int]:
    blob = f"{person['name']} {person['id']}".lower()
    for keywords, depth in ROLE_DEPTH_HINTS:
        if any(k in blob for k in keywords):
            return depth
    return None


def solve_generations(graph: FamilyGraph, trace: PedigreeTrace) -> Dict[str, int]:
    """Assign a generation index to every individual.

    Runs a BFS per connected component so nothing is left unassigned, then
    anchors the components against each other using role hints. Contradictory
    constraints are reported rather than silently applied.
    """
    generation: Dict[str, int] = {}
    conflicts: List[Dict[str, Any]] = []

    for comp in graph.components():
        seed = comp[0]
        # Prefer seeding from someone with parents recorded — it makes the
        # relative numbering inside the component more stable.
        for pid in comp:
            if graph.parents[pid]:
                seed = pid
                break

        local: Dict[str, int] = {seed: 0}
        queue = [seed]
        while queue:
            cur = queue.pop(0)
            level = local[cur]
            neighbours = (
                [(p, level - 1) for p in graph.parents[cur]] +
                [(c, level + 1) for c in graph.children[cur]] +
                [(s, level) for s in graph.spouses[cur]] +
                [(s, level) for s in graph.siblings[cur]]
            )
            for other, expected in neighbours:
                if other not in local:
                    local[other] = expected
                    queue.append(other)
                elif local[other] != expected:
                    conflicts.append({
                        "between": [cur, other],
                        "assigned": local[other],
                        "implied": expected,
                    })

        base = min(local.values())
        for pid, level in local.items():
            generation[pid] = level - base

        # Anchor this component against the role hints so a disconnected branch
        # lands in the row its relationship names imply.
        hints = [(pid, _role_hint(graph.people[pid])) for pid in comp]
        offsets = [hint - generation[pid] for pid, hint in hints if hint is not None]
        if offsets:
            offsets.sort()
            shift = offsets[len(offsets) // 2]
            for pid in comp:
                generation[pid] += shift
            trace.event("generations", "Anchored component using role hints", {
                "size": len(comp), "shift": shift,
                "members": comp[:8],
            })

    if conflicts:
        trace.warn("generations",
                   f"{len(conflicts)} contradictory generation constraint(s); "
                   "kept the first assignment for each",
                   {"conflicts": conflicts[:6]})

    if generation:
        floor = min(generation.values())
        for pid in generation:
            generation[pid] -= floor

    if len(graph.components()) > 1:
        trace.warn("generations",
                   f"Pedigree has {len(graph.components())} disconnected components — "
                   "some relatives have no path to the proband",
                   {"components": [c[:6] for c in graph.components()]})

    trace.event("generations", "Generations solved", {
        "levels": sorted(set(generation.values())),
        "assignment": generation,
    })
    return generation


# ── blocks (rigid spouse groups) ───────────────────────────────────────────

@dataclass
class Block:
    """A run of individuals that must stay adjacent — a couple, or a chain for
    someone with multiple partners. Laid out as one rigid unit."""
    members: List[str]
    offsets: List[float]        # relative to block centre
    generation: int
    x: float = 0.0

    @property
    def key(self) -> str:
        return "|".join(self.members)

    def position_of(self, pid: str) -> float:
        return self.x + self.offsets[self.members.index(pid)]

    def half_width(self, extents: Dict[str, Tuple[float, float]]) -> Tuple[float, float]:
        lefts = [self.offsets[i] - extents[m][0] for i, m in enumerate(self.members)]
        rights = [self.offsets[i] + extents[m][1] for i, m in enumerate(self.members)]
        return (-min(lefts), max(rights))


def build_blocks(graph: FamilyGraph, generation: Dict[str, int],
                 nodes: Dict[str, NodeBox], extents: Dict[str, Tuple[float, float]],
                 trace: PedigreeTrace) -> List[Block]:
    """Group same-generation spouses into rigid blocks.

    Married-in partners sit on the outer edge of a sibling cluster so sibship
    lines never have to cross a spouse to reach a brother or sister. Someone
    with two partners is placed *between* them, so neither marriage bar has to
    cross the other spouse's symbol.
    """
    blocks: List[Block] = []
    placed: Set[str] = set()

    def partner_count(pid: str) -> int:
        return sum(1 for s in graph.spouses[pid] if generation.get(s) == generation[pid])

    # People with more than one partner are blocked first, so the shared partner
    # ends up in the middle of the chain instead of whichever spouse happened to
    # be listed first.
    processing_order = sorted(graph.order, key=lambda p: -partner_count(p))

    for pid in processing_order:
        if pid in placed:
            continue
        gen = generation[pid]
        partners = [s for s in graph.spouses[pid]
                    if s not in placed and generation.get(s) == gen]
        if not partners:
            blocks.append(Block([pid], [0.0], gen))
            placed.add(pid)
            continue

        if len(partners) >= 2:
            # Shared partner sits in the middle of the chain.
            chain = [partners[0], pid, partners[1]]
        else:
            chain = [pid, partners[0]]
            a, b = chain
            blood = {m for m in chain if graph.parents[m] or graph.siblings[m]}
            # Put the blood relative on the side facing the rest of their sibship.
            if b in blood and a not in blood:
                chain = [b, a]
            elif (a in blood) == (b in blood):
                chain = [a, b] if graph.people[a]["gender"] == "male" else [b, a]

        spacing: List[float] = [0.0]
        for i in range(1, len(chain)):
            prev, cur = chain[i - 1], chain[i]
            gap = max(
                COUPLE_GAP,
                extents[prev][1] + extents[cur][0] + 14.0,
                # The marriage bar's midpoint carries the descent line, so both
                # labels have to clear it.
                nodes[prev].label_width + 2 * LABEL_CLEARANCE,
                nodes[cur].label_width + 2 * LABEL_CLEARANCE,
            )
            spacing.append(spacing[-1] + gap)
        centre = sum(spacing) / len(spacing)
        offsets = [s - centre for s in spacing]

        blocks.append(Block(chain, offsets, gen))
        placed.update(chain)

    trace.event("blocks", "Rigid spouse blocks built", {
        "count": len(blocks),
        "couples": sum(1 for b in blocks if len(b.members) > 1),
    })
    return blocks


# ── ordering ───────────────────────────────────────────────────────────────

def order_blocks(graph: FamilyGraph, blocks: List[Block],
                 trace: PedigreeTrace) -> Dict[int, List[Block]]:
    """Order blocks left-to-right within each generation, minimising crossings.

    Seeds from input order (the model is prompted to emit left-to-right), then
    runs median-heuristic sweeps in both directions — the ordering phase of a
    standard layered drawing.
    """
    by_gen: Dict[int, List[Block]] = {}
    for block in blocks:
        by_gen.setdefault(block.generation, []).append(block)

    block_of: Dict[str, Block] = {m: b for b in blocks for m in b.members}
    input_rank = {pid: i for i, pid in enumerate(graph.order)}
    for gen in by_gen:
        by_gen[gen].sort(key=lambda b: min(input_rank[m] for m in b.members))

    # Paternal branch left, maternal branch right, anchored on the proband.
    proband = next((p for p in graph.order if graph.people[p]["proband"]), None)
    side: Dict[str, int] = {}
    if proband:
        father = next((p for p in graph.parents[proband]
                       if graph.people[p]["gender"] == "male"), None)
        mother = next((p for p in graph.parents[proband]
                       if graph.people[p]["gender"] == "female"), None)

        def mark(root: Optional[str], value: int) -> None:
            if not root:
                return
            stack, seen = [root], set()
            while stack:
                cur = stack.pop()
                if cur in seen:
                    continue
                seen.add(cur)
                side[cur] = value
                stack.extend(graph.parents[cur])
                stack.extend(graph.siblings[cur])
                for sib in graph.siblings[cur]:
                    stack.extend(graph.spouses[sib])

        mark(father, -1)
        mark(mother, 1)
        for gen in by_gen:
            by_gen[gen].sort(key=lambda b: (
                sum(side.get(m, 0) for m in b.members) / len(b.members),
                min(input_rank[m] for m in b.members),
            ))

    def median_key(block: Block, neighbour_pos: Dict[str, float],
                   relation: str) -> float:
        values: List[float] = []
        for member in block.members:
            related = graph.parents[member] if relation == "up" else graph.children[member]
            values.extend(neighbour_pos[r] for r in related if r in neighbour_pos)
        if not values:
            return neighbour_pos.get(block.members[0], float("inf"))
        values.sort()
        return values[len(values) // 2]

    levels = sorted(by_gen)
    for sweep in range(4):
        sequence = levels[1:] if sweep % 2 == 0 else list(reversed(levels[:-1]))
        relation = "up" if sweep % 2 == 0 else "down"
        for gen in sequence:
            reference = gen - 1 if relation == "up" else gen + 1
            if reference not in by_gen:
                continue
            positions = {m: float(i)
                         for i, b in enumerate(by_gen[reference])
                         for m in b.members}
            current = {b.key: i for i, b in enumerate(by_gen[gen])}
            by_gen[gen].sort(key=lambda b: (
                median_key(b, positions, relation) if median_key(b, positions, relation) != float("inf")
                else current[b.key],
                current[b.key],
            ))

    orient_couples(graph, by_gen)

    trace.event("ordering", "Block order resolved", {
        str(gen): [b.members for b in by_gen[gen]] for gen in sorted(by_gen)
    })
    return by_gen


def orient_couples(graph: FamilyGraph, by_gen: Dict[int, List[Block]]) -> None:
    """Turn each couple so the blood relative faces their own family.

    Which side a married-in spouse belongs on depends on where the blood
    relative's parents and siblings ended up, so this can only be decided once
    the row order exists. Getting it wrong strands a spouse between two
    siblings, which is what the ordering rules are meant to prevent.
    """
    def normalised_index(pid: str) -> Optional[float]:
        for row in by_gen.values():
            for index, block in enumerate(row):
                if pid in block.members:
                    return 0.5 if len(row) == 1 else index / (len(row) - 1)
        return None

    for row in by_gen.values():
        for index, block in enumerate(row):
            if len(block.members) != 2:
                continue
            own = 0.5 if len(row) == 1 else index / (len(row) - 1)

            def pull(member: str) -> Optional[float]:
                targets = [normalised_index(r) for r in
                           graph.parents[member] + sorted(graph.siblings[member])]
                targets = [t for t in targets if t is not None]
                return sum(targets) / len(targets) if targets else None

            a, b = block.members
            pull_a, pull_b = pull(a), pull(b)

            if (pull_a is None) == (pull_b is None):
                continue                      # both or neither are blood relatives

            anchored, pull_value = (a, pull_a) if pull_b is None else (b, pull_b)
            wants_right = pull_value > own
            currently_right = block.members[1] == anchored
            if wants_right != currently_right:
                block.members.reverse()


# ── x assignment ───────────────────────────────────────────────────────────

def _isotonic(values: List[float], lower_offsets: List[float]) -> List[float]:
    """Exact L2 projection onto ``x[i] + gap[i] <= x[i+1]``.

    Substituting ``z[i] = x[i] - lower_offsets[i]`` turns the gap constraints
    into a plain monotonicity constraint, which pool-adjacent-violators solves
    optimally in linear time. This keeps nodes as close to their barycentre as
    the spacing rules allow, instead of shoving everything right.
    """
    shifted = [v - o for v, o in zip(values, lower_offsets)]
    blocks: List[List[float]] = []          # [sum, count]
    for value in shifted:
        blocks.append([value, 1.0])
        while len(blocks) > 1 and blocks[-2][0] / blocks[-2][1] > blocks[-1][0] / blocks[-1][1]:
            total, count = blocks.pop()
            blocks[-1][0] += total
            blocks[-1][1] += count
    out: List[float] = []
    for total, count in blocks:
        out.extend([total / count] * int(count))
    return [z + o for z, o in zip(out, lower_offsets)]


def _separate(row: List[Block], desired: Dict[str, float],
              extents: Dict[str, Tuple[float, float]]) -> None:
    """Apply desired positions to a row, then enforce minimum gaps exactly."""
    if not row:
        return
    values = [desired.get(b.key, b.x) for b in row]
    offsets = [0.0]
    for i in range(1, len(row)):
        _, prev_right = row[i - 1].half_width(extents)
        cur_left, _ = row[i].half_width(extents)
        offsets.append(offsets[-1] + prev_right + cur_left + MIN_GAP)
    for block, x in zip(row, _isotonic(values, offsets)):
        block.x = x


def assign_x(graph: FamilyGraph, by_gen: Dict[int, List[Block]],
             extents: Dict[str, Tuple[float, float]], trace: PedigreeTrace) -> None:
    """Alternating barycenter passes with exact separation after each."""
    levels = sorted(by_gen)

    for gen in levels:
        _separate(by_gen[gen], {}, extents)

    def member_x() -> Dict[str, float]:
        return {m: b.position_of(m)
                for row in by_gen.values() for b in row for m in b.members}

    for iteration in range(14):
        positions = member_x()

        # Pull children under their parents.
        for gen in levels[1:]:
            desired: Dict[str, float] = {}
            for block in by_gen[gen]:
                anchors: List[float] = []
                for member in block.members:
                    parents = [positions[p] for p in graph.parents[member] if p in positions]
                    if parents:
                        offset = block.offsets[block.members.index(member)]
                        anchors.append(sum(parents) / len(parents) - offset)
                if anchors:
                    desired[block.key] = sum(anchors) / len(anchors)
                else:
                    desired[block.key] = block.x
            _separate(by_gen[gen], desired, extents)
            positions = member_x()

        # Pull parents over the middle of their children.
        for gen in reversed(levels[:-1]):
            desired = {}
            for block in by_gen[gen]:
                kids = [positions[c] for m in block.members
                        for c in graph.children[m] if c in positions]
                desired[block.key] = (sum(kids) / len(kids)) if kids else block.x
            _separate(by_gen[gen], desired, extents)
            positions = member_x()

    # Deliberately no per-row re-centring here: nudging a narrow row toward the
    # drawing's centre looks tidier in isolation but pulls children out from
    # under their parents, which is the one alignment that actually matters.

    trace.event("x_assign", "Horizontal positions solved", {
        str(gen): {m: round(b.position_of(m), 1) for b in by_gen[gen] for m in b.members}
        for gen in levels
    })


# ── edge routing ───────────────────────────────────────────────────────────

def route_edges(graph: FamilyGraph, nodes: Dict[str, NodeBox],
                trace: PedigreeTrace) -> List[Segment]:
    """Marriage bars, descent lines and shared sibship buses.

    Sibship buses within one generation gap are interval-coloured onto distinct
    y levels, so two families' buses can never be drawn on top of each other.
    """
    segments: List[Segment] = []

    # -- marriage bars --
    drawn: Set[Tuple[str, str]] = set()
    for pid in graph.order:
        for spouse in graph.spouses[pid]:
            pair = tuple(sorted((pid, spouse)))
            if pair in drawn or pid not in nodes or spouse not in nodes:
                continue
            drawn.add(pair)
            a, b = nodes[pair[0]], nodes[pair[1]]
            if abs(a.y - b.y) > 1:
                trace.warn("routing", f"Spouses '{a.id}' and '{b.id}' are on different rows")
                continue
            left, right = (a, b) if a.x <= b.x else (b, a)
            consanguineous = bool(graph.ancestors(left.id) & graph.ancestors(right.id))
            kind = "consanguineous" if consanguineous else "marriage"
            segments.append(Segment(kind, [(left.right, left.y), (right.left, right.y)],
                                    {"pair": list(pair)}))
            if consanguineous:
                trace.event("routing", f"Consanguineous union: {left.id} × {right.id}")

    # -- descent + sibship buses, one generation gap at a time --
    unions = graph.unions()
    gap_groups: Dict[int, List[Tuple[Tuple[str, ...], List[str]]]] = {}
    for parents, kids in unions:
        visible = [k for k in kids if k in nodes]
        present = [p for p in parents if p in nodes]
        if not visible or not present:
            continue
        gap_groups.setdefault(nodes[visible[0]].generation, []).append((tuple(present), visible))

    for child_gen, group in sorted(gap_groups.items()):
        child_top = min(nodes[k].top for _, kids in group for k in kids)
        parent_bottom = max(nodes[p].label_bottom for parents, _ in group for p in parents)
        gap_start = parent_bottom + 10
        gap_end = child_top - 12
        if gap_end <= gap_start:                     # degenerate; fall back to midpoint
            gap_start = gap_end = (parent_bottom + child_top) / 2

        # Interval-colour the buses so overlapping spans get separate levels.
        entries = []
        for parents, kids in group:
            xs = [nodes[k].x for k in kids]
            if len(parents) >= 2:
                pxs = sorted(nodes[p].x for p in parents)
                descent_x = (pxs[0] + pxs[-1]) / 2
                descent_y = nodes[parents[0]].y
            else:
                descent_x = nodes[parents[0]].x
                descent_y = nodes[parents[0]].bottom
            span = (min(xs + [descent_x]), max(xs + [descent_x]))
            entries.append({"parents": parents, "kids": kids, "xs": xs,
                            "descent_x": descent_x, "descent_y": descent_y, "span": span})

        entries.sort(key=lambda e: e["span"][0])
        levels: List[List[Tuple[float, float]]] = []
        for entry in entries:
            for level_index, spans in enumerate(levels):
                if all(entry["span"][1] < s[0] - 6 or entry["span"][0] > s[1] + 6 for s in spans):
                    spans.append(entry["span"])
                    entry["level"] = level_index
                    break
            else:
                entry["level"] = len(levels)
                levels.append([entry["span"]])

        level_count = max(len(levels), 1)
        for entry in entries:
            slot = (entry["level"] + 1) / (level_count + 1)
            bus_y = gap_start + (gap_end - gap_start) * slot
            descent_x, descent_y = entry["descent_x"], entry["descent_y"]
            kids, xs = entry["kids"], entry["xs"]

            single_straight = len(kids) == 1 and abs(xs[0] - descent_x) < 0.5
            if single_straight:
                segments.append(Segment("descent",
                                        [(descent_x, descent_y), (descent_x, nodes[kids[0]].top)],
                                        {"union": list(entry["parents"])}))
                continue

            segments.append(Segment("descent", [(descent_x, descent_y), (descent_x, bus_y)],
                                    {"union": list(entry["parents"])}))
            segments.append(Segment("sibship",
                                    [(min(xs + [descent_x]), bus_y), (max(xs + [descent_x]), bus_y)],
                                    {"union": list(entry["parents"]), "level": entry["level"]}))
            for kid in kids:
                segments.append(Segment("drop",
                                        [(nodes[kid].x, bus_y), (nodes[kid].x, nodes[kid].top)],
                                        {"child": kid}))

        if level_count > 1:
            trace.event("routing", f"Generation gap above row {child_gen} uses "
                                   f"{level_count} sibship bus levels")

    trace.event("routing", "Connectors routed", {
        "segments": len(segments),
        "by_kind": {k: sum(1 for s in segments if s.kind == k)
                    for k in {s.kind for s in segments}},
    })
    return segments


# ── entry point ────────────────────────────────────────────────────────────

def compute_layout(individuals: Sequence[Dict[str, Any]],
                   relationships: Sequence[Dict[str, Any]],
                   trace: Optional[PedigreeTrace] = None) -> PedigreeLayout:
    """Build a fully-resolved pedigree layout from a raw family graph."""
    trace = trace or null_trace()

    with trace.stage("graph", "Normalising family graph",
                     {"individuals": len(individuals), "relationships": len(relationships)}):
        graph = FamilyGraph(individuals, relationships, trace)

    if not graph.order:
        trace.warn("layout", "No individuals to lay out")
        return PedigreeLayout(320, 140, [], [], {}, ["Pedigree contained no individuals."])

    with trace.stage("generations", "Solving generation levels"):
        generation = solve_generations(graph, trace)

    # A parent recorded without a partner carries the descent line on their own
    # centre line, which would run straight through a centred name label — so
    # their label is nudged aside and the room for it reserved up front.
    solo_parents = {parents[0] for parents, kids in graph.unions()
                    if len(parents) == 1 and kids}

    nodes: Dict[str, NodeBox] = {}
    extents: Dict[str, Tuple[float, float]] = {}
    for pid in graph.order:
        person = graph.people[pid]
        lines = wrap_label(person["name"])
        label_width = max([text_width(line, NAME_FONT) for line in lines] or [0.0])
        if person["age"] is not None:
            label_width = max(label_width, text_width(f"{person['age']}y", AGE_FONT))
        node = NodeBox(
            id=pid, name=person["name"], gender=person["gender"],
            status=person["status"], deceased=person["deceased"],
            proband=person["proband"], generation=generation[pid],
            age=person["age"], conditions=person["conditions"],
            label_lines=lines, label_width=label_width,
        )
        if pid in solo_parents:
            node.label_dx = LABEL_CLEARANCE + label_width / 2
        nodes[pid] = node

        left, right = node.extents()
        if node.proband:
            # The proband arrow hangs off the lower-left corner; reserve its room
            # so it cannot run into the neighbour's name.
            left = max(left, SYMBOL / 2 + PROBAND_ARROW_REACH)
        extents[pid] = (left, right)

    with trace.stage("blocks", "Grouping spouses into rigid blocks"):
        blocks = build_blocks(graph, generation, nodes, extents, trace)

    with trace.stage("ordering", "Reducing edge crossings"):
        by_gen = order_blocks(graph, blocks, trace)

    with trace.stage("x_assign", "Solving horizontal positions"):
        assign_x(graph, by_gen, extents, trace)

    # Rows are spaced by the tallest label block in the row above, so labels can
    # never collide with the row beneath them.
    row_y: Dict[int, float] = {}
    cursor = 0.0
    for gen in sorted(by_gen):
        row_y[gen] = cursor
        tallest = max((nodes[m].label_height for b in by_gen[gen] for m in b.members),
                      default=0.0)
        cursor += max(ROW_SPACING, SYMBOL + LABEL_TOP_PAD + tallest + 74.0)

    for gen, row in by_gen.items():
        for block in row:
            for member in block.members:
                nodes[member].x = block.position_of(member)
                nodes[member].y = row_y[gen]

    with trace.stage("routing", "Routing connectors"):
        segments = route_edges(graph, nodes, trace)

    # Size the canvas to the content — the old renderer used a fixed 1200×800
    # and left roughly half of every chart blank.
    all_nodes = list(nodes.values())
    xs0 = [n.bounds()[0] for n in all_nodes] + [p[0] for s in segments for p in s.points]
    ys0 = [n.bounds()[1] for n in all_nodes] + [p[1] for s in segments for p in s.points]
    xs1 = [n.bounds()[2] for n in all_nodes] + [p[0] for s in segments for p in s.points]
    ys1 = [n.bounds()[3] for n in all_nodes] + [p[1] for s in segments for p in s.points]

    dx = PADDING - min(xs0)
    dy = PADDING - min(ys0)
    for node in all_nodes:
        node.x += dx
        node.y += dy
    for segment in segments:
        segment.points = [(px + dx, py + dy) for px, py in segment.points]

    width = math.ceil(max(xs1) - min(xs0) + PADDING * 2)
    height = math.ceil(max(ys1) - min(ys0) + PADDING * 2)

    generations_map: Dict[int, List[str]] = {}
    for gen in sorted(by_gen):
        generations_map[gen] = [m for b in by_gen[gen] for m in b.members]

    layout = PedigreeLayout(
        width=float(width), height=float(height),
        nodes=sorted(all_nodes, key=lambda n: (n.generation, n.x)),
        segments=segments, generations=generations_map,
        warnings=list(trace.warnings),
    )
    trace.event("layout", "Layout complete", {
        "canvas": [layout.width, layout.height],
        "nodes": len(layout.nodes),
        "segments": len(layout.segments),
        "generations": {str(g): len(v) for g, v in generations_map.items()},
    })
    return layout
