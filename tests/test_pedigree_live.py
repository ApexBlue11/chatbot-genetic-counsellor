"""
Live end-to-end check: natural language → Gemini → layout → validated SVG.

This is the only pedigree suite that hits the network, so it is kept separate
from the offline loop and run deliberately rather than on every edit.

    python tests/test_pedigree_live.py

Each scenario asserts the properties that actually matter clinically — everyone
described is present, the family is fully connected, relatives sit on the right
rows — rather than pinning exact wording the model is free to vary.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

from analysis.pedigree_generator import PedigreeGenerator          # noqa: E402
from analysis.pedigree_layout import FamilyGraph, compute_layout   # noqa: E402
from analysis.pedigree_logging import PedigreeTrace, null_trace    # noqa: E402
from analysis.pedigree_svg import render_svg                       # noqa: E402
from analysis.pedigree_validator import validate_layout            # noqa: E402
from core.gemini_client import load_gemini_api_key                 # noqa: E402

OUT_DIR = os.path.join("tests", "pedigree_out", "live")

SCENARIOS = [
    {
        "name": "cousins_maternal",
        "description": (
            "The proband is an 8-year-old boy with cystic fibrosis. His father is "
            "an unaffected carrier and his mother is an unaffected carrier. The "
            "mother has an older brother (the proband's uncle) who is unaffected "
            "and married to an unaffected aunt; they have one daughter, the "
            "proband's cousin, who is 11 and unaffected. The maternal "
            "grandparents are both alive and unaffected."
        ),
        "expect_people": ["proband", "father", "mother", "uncle", "aunt", "cousin"],
        "expect_same_row": [["proband", "cousin"], ["mother", "uncle"]],
        "expect_connected": True,
        "min_generations": 3,
    },
    {
        "name": "dominant_three_generations",
        "description": (
            "A 34-year-old woman is affected with Huntington disease. Her father "
            "was also affected and died at 58. Her paternal grandmother was "
            "affected. The woman has two children: a 6-year-old son of unknown "
            "status and a 9-year-old daughter who is unaffected. Her husband is "
            "unaffected."
        ),
        "expect_people": ["father", "grandmother"],
        "expect_connected": True,
        "min_generations": 4,
    },
    {
        "name": "consanguineous_trio",
        "description": (
            "Two first cousins married. They have one affected daughter with a "
            "rare recessive condition. Both parents are unaffected carriers. The "
            "cousins' fathers are brothers, and both of those brothers are alive."
        ),
        "expect_people": [],
        "expect_connected": True,
        "min_generations": 3,
    },
]


def row_of(layout, needle):
    """Generation of the individual a role word refers to.

    Matching is on whole words and prefers an exact name, so "mother" resolves
    to "Proband's Mother" rather than "Maternal Grandmother", and "proband" to
    "Proband" rather than "Proband's Father".
    """
    import re

    target = needle.lower()
    for node in layout.nodes:
        if node.id.lower() == target or node.name.lower() == target:
            return node.generation

    pattern = re.compile(rf"\b{re.escape(target)}\b")
    matches = [n for n in layout.nodes
               if pattern.search(n.name.lower()) or pattern.search(n.id.lower().replace("_", " "))]
    if not matches:
        return None
    # Shortest name is the most specific match.
    return min(matches, key=lambda n: len(n.name)).generation


def run_scenario(generator, scenario):
    problems = []
    trace = PedigreeTrace(f"live-{scenario['name']}")

    data = generator.parse_family_description(scenario["description"], use_ai=True, trace=trace)
    layout = compute_layout(data["individuals"], data["relationships"], trace)
    report = validate_layout(layout, data["individuals"], data["relationships"])
    svg = render_svg(layout, title=f"Pedigree — {scenario['name']}")

    os.makedirs(OUT_DIR, exist_ok=True)
    with open(os.path.join(OUT_DIR, f"{scenario['name']}.svg"), "w", encoding="utf-8") as fh:
        fh.write(svg)

    problems += [str(issue) for issue in report.errors]

    for person in scenario["expect_people"]:
        if row_of(layout, person) is None:
            problems.append(f"'{person}' is missing from the chart")

    for group in scenario.get("expect_same_row", []):
        rows = {p: row_of(layout, p) for p in group}
        present = {p: r for p, r in rows.items() if r is not None}
        if len(set(present.values())) > 1:
            problems.append(f"{group} should share a generation, got {present}")

    if scenario.get("expect_connected"):
        graph = FamilyGraph(data["individuals"], data["relationships"], null_trace())
        components = graph.components()
        if len(components) > 1:
            problems.append(
                f"family split into {len(components)} disconnected groups: "
                f"{[c[:5] for c in components]}"
            )

    minimum = scenario.get("min_generations")
    if minimum and len(layout.generations) < minimum:
        problems.append(f"expected at least {minimum} generations, got {len(layout.generations)}")

    trace.finish()
    return layout, report, svg, problems


def main():
    key = load_gemini_api_key()
    if not key:
        print("No Gemini API key found (api_key/gemini_key.txt or GEMINI_API_KEY).")
        return 2

    generator = PedigreeGenerator(api_key=key)
    failures = []

    print(f"Live pedigree pipeline — {len(SCENARIOS)} scenario(s)\n" + "=" * 70)

    for scenario in SCENARIOS:
        print(f"\n{scenario['name']}")
        try:
            layout, report, svg, problems = run_scenario(generator, scenario)
            print(f"  {len(layout.nodes)} individuals, {len(layout.generations)} generations, "
                  f"{len(svg)} bytes of SVG — geometry {report.summary()}")
            print("  rows: " + ", ".join(
                f"{n.name}={n.generation}" for n in sorted(layout.nodes, key=lambda n: (n.generation, n.x))
            ))
            for issue in report.warnings:
                print(f"    warn: {issue.message}")
        except Exception as exc:                                  # noqa: BLE001
            import traceback
            traceback.print_exc()
            problems = [f"raised {type(exc).__name__}: {exc}"]

        if problems:
            failures.append(scenario["name"])
            for problem in problems:
                print(f"    FAIL: {problem}")
        else:
            print("    PASS")

    print("\n" + "=" * 70)
    print(f"{len(SCENARIOS) - len(failures)} passed, {len(failures)} failed")
    print(f"SVGs written to {OUT_DIR}/")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
