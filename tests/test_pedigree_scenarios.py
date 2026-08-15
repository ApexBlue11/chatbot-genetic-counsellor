"""
Integration check for the PedigreeGenerator API surface.

Where tests/test_pedigree_layout.py exercises the layout engine directly, this
covers the layer the backend actually calls — PedigreeGenerator.generate_svg —
across a set of clinical scenarios, and asserts the emitted SVG is well-formed
and geometrically clean.

    python tests/test_pedigree_scenarios.py
"""

import os
import sys
import xml.etree.ElementTree as ET

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("VARIANTMIND_PEDIGREE_LOG", "0")

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

from analysis.pedigree_generator import PedigreeGenerator          # noqa: E402
from analysis.pedigree_validator import validate_layout            # noqa: E402

OUT_DIR = os.path.join("tests", "scenarios_out")

SCENARIOS = {
    "scenario_a_nuclear_ar": {
        "individuals": [
            {"id": "father", "name": "Father", "gender": "male", "status": "carrier"},
            {"id": "mother", "name": "Mother", "gender": "female", "status": "carrier"},
            {"id": "proband", "name": "Proband", "gender": "male", "status": "affected"},
            {"id": "sister", "name": "Sister", "gender": "female", "status": "unaffected"},
        ],
        "relationships": [
            {"type": "marriage", "person1": "father", "person2": "mother"},
            {"type": "parent-child", "person1": "father", "person2": "proband"},
            {"type": "parent-child", "person1": "mother", "person2": "proband"},
            {"type": "parent-child", "person1": "father", "person2": "sister"},
            {"type": "parent-child", "person1": "mother", "person2": "sister"},
        ],
    },
    "scenario_b_three_generations": {
        "individuals": [
            {"id": "gf", "name": "Grandfather", "gender": "male", "status": "affected",
             "deceased": True},
            {"id": "gm", "name": "Grandmother", "gender": "female", "status": "unaffected"},
            {"id": "mother", "name": "Mother", "gender": "female", "status": "carrier"},
            {"id": "father", "name": "Father", "gender": "male", "status": "unaffected"},
            {"id": "proband", "name": "Proband", "gender": "male", "status": "affected"},
        ],
        "relationships": [
            {"type": "marriage", "person1": "gf", "person2": "gm"},
            {"type": "parent-child", "person1": "gf", "person2": "mother"},
            {"type": "parent-child", "person1": "gm", "person2": "mother"},
            {"type": "marriage", "person1": "father", "person2": "mother"},
            {"type": "parent-child", "person1": "father", "person2": "proband"},
            {"type": "parent-child", "person1": "mother", "person2": "proband"},
        ],
    },
    "scenario_c_consanguineous": {
        "individuals": [
            {"id": "uncle", "name": "Uncle", "gender": "male", "status": "unaffected"},
            {"id": "aunt", "name": "Aunt", "gender": "female", "status": "unaffected"},
            {"id": "husband", "name": "Husband (Cousin 1)", "gender": "male", "status": "carrier"},
            {"id": "wife", "name": "Wife (Cousin 2)", "gender": "female", "status": "carrier"},
            {"id": "child", "name": "Affected Child", "gender": "female", "status": "affected"},
        ],
        "relationships": [
            {"type": "marriage", "person1": "uncle", "person2": "aunt"},
            {"type": "parent-child", "person1": "uncle", "person2": "husband"},
            {"type": "parent-child", "person1": "aunt", "person2": "husband"},
            {"type": "parent-child", "person1": "uncle", "person2": "wife"},
            {"type": "parent-child", "person1": "aunt", "person2": "wife"},
            {"type": "marriage", "person1": "husband", "person2": "wife"},
            {"type": "parent-child", "person1": "husband", "person2": "child"},
            {"type": "parent-child", "person1": "wife", "person2": "child"},
        ],
    },
    "scenario_d_x_linked": {
        "individuals": [
            {"id": "father", "name": "Father", "gender": "male", "status": "unaffected"},
            {"id": "mother", "name": "Mother (Carrier)", "gender": "female", "status": "carrier"},
            {"id": "proband", "name": "Proband", "gender": "male", "status": "affected"},
            {"id": "sister", "name": "Sister (Carrier)", "gender": "female", "status": "carrier"},
        ],
        "relationships": [
            {"type": "marriage", "person1": "father", "person2": "mother"},
            {"type": "parent-child", "person1": "father", "person2": "proband"},
            {"type": "parent-child", "person1": "mother", "person2": "proband"},
            {"type": "parent-child", "person1": "father", "person2": "sister"},
            {"type": "parent-child", "person1": "mother", "person2": "sister"},
        ],
    },
    "scenario_e_mixed_symbols": {
        "individuals": [
            {"id": "p1", "name": "Deceased Grandfather", "gender": "male",
             "status": "unaffected", "deceased": True},
            {"id": "p2", "name": "Grandmother", "gender": "female", "status": "unknown"},
            {"id": "carrier_son", "name": "Carrier Son", "gender": "male", "status": "carrier"},
            {"id": "unknown_carrier", "name": "Unknown Sex", "gender": "unknown",
             "status": "carrier"},
        ],
        "relationships": [
            {"type": "marriage", "person1": "p1", "person2": "p2"},
            {"type": "parent-child", "person1": "p1", "person2": "carrier_son"},
            {"type": "parent-child", "person1": "p2", "person2": "carrier_son"},
            {"type": "parent-child", "person1": "p1", "person2": "unknown_carrier"},
            {"type": "parent-child", "person1": "p2", "person2": "unknown_carrier"},
        ],
    },
}


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    generator = PedigreeGenerator()          # no API key: no network, no extraction
    failures = []

    print(f"Pedigree scenario suite — {len(SCENARIOS)} scenario(s)\n" + "=" * 68)

    for name, data in SCENARIOS.items():
        problems = []
        try:
            layout = generator.build_layout(data)
            report = validate_layout(layout, data["individuals"], data["relationships"])
            svg = generator.generate_svg(data, title=f"Pedigree — {name}")

            path = os.path.join(OUT_DIR, f"{name}.svg")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(svg)

            # Parsing proves the document is well-formed XML, not just a string.
            ET.fromstring(svg)

            problems = [str(issue) for issue in report.errors]
            if len(layout.nodes) != len(data["individuals"]):
                problems.append(f"expected {len(data['individuals'])} individuals, "
                                f"laid out {len(layout.nodes)}")
            for node in layout.nodes:
                if node.gender not in ("male", "female", "unknown"):
                    problems.append(f"invalid gender '{node.gender}' on {node.id}")
                if node.status not in ("affected", "carrier", "unaffected", "unknown"):
                    problems.append(f"invalid status '{node.status}' on {node.id}")

            print(f"  {'PASS' if not problems else 'FAIL'}  {name:<30} "
                  f"{len(layout.nodes)} nodes, {len(svg)} bytes of SVG")
        except Exception as exc:                                  # noqa: BLE001
            problems = [f"raised {type(exc).__name__}: {exc}"]
            print(f"  FAIL  {name:<30} {problems[0]}")

        for problem in problems:
            print(f"          → {problem}")
        if problems:
            failures.append(name)

    print("=" * 68)
    print(f"{len(SCENARIOS) - len(failures)} passed, {len(failures)} failed")
    print(f"SVGs written to {OUT_DIR}/")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
