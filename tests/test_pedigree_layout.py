"""
Offline regression suite for the pedigree layout engine.

Runs every fixture through layout → validation → SVG render, and fails on any
validator error. No network calls, fully deterministic, so it can be run on
every edit as the inner iteration loop.

    python tests/test_pedigree_layout.py            # run everything
    python tests/test_pedigree_layout.py nuclear_ar # run one fixture
    python tests/test_pedigree_layout.py -v         # include the full trace

Rendered SVGs land in tests/pedigree_out/ for eyeballing; the pass/fail decision
never depends on looking at them.
"""

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("VARIANTMIND_PEDIGREE_LOG", "0")

# The default Windows console codepage is cp1252 and chokes on the box-drawing
# and arrow characters used below.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

from analysis.pedigree_layout import compute_layout                # noqa: E402
from analysis.pedigree_logging import PedigreeTrace                # noqa: E402
from analysis.pedigree_svg import render_svg                       # noqa: E402
from analysis.pedigree_validator import format_report, validate_layout  # noqa: E402
from tests.pedigree_fixtures import FIXTURES                       # noqa: E402

OUT_DIR = os.path.join("tests", "pedigree_out")


def check_expectations(name, layout, report, expectations):
    """Fixture-specific assertions layered on top of the geometric checks."""
    failures = []

    expected_individuals = expectations.get("individuals")
    if expected_individuals is not None and len(layout.nodes) != expected_individuals:
        failures.append(f"expected {expected_individuals} individuals, laid out {len(layout.nodes)}")

    expected_generations = expectations.get("generations")
    if expected_generations is not None and len(layout.generations) != expected_generations:
        failures.append(f"expected {expected_generations} generations, "
                        f"got {len(layout.generations)} ({sorted(layout.generations)})")

    for group in expectations.get("same_generation", []):
        levels = {}
        for pid in group:
            node = layout.node(pid)
            if node is None:
                failures.append(f"'{pid}' is missing from the layout")
            else:
                levels[pid] = node.generation
        if len(set(levels.values())) > 1:
            failures.append(f"{group} should share a generation, got {levels}")

    if expectations.get("consanguineous") and \
            not any(s.kind == "consanguineous" for s in layout.segments):
        failures.append("expected a consanguineous (double-bar) marriage line")

    expected_proband = expectations.get("proband")
    if expected_proband:
        marked = [n.id for n in layout.nodes if n.proband]
        if marked != [expected_proband]:
            failures.append(f"expected only '{expected_proband}' marked as proband, got {marked}")

    # Disconnected input is tolerated, but only where the fixture says so.
    if not expectations.get("allow_disconnected") and \
            any(i.code == "disconnected" for i in report.warnings):
        failures.append("layout split into disconnected components")

    return failures


def run(selected=None, verbose=False):
    os.makedirs(OUT_DIR, exist_ok=True)
    names = [selected] if selected else list(FIXTURES)
    if selected and selected not in FIXTURES:
        print(f"Unknown fixture '{selected}'. Available: {', '.join(FIXTURES)}")
        return 2

    passed, failed = [], []
    started = time.perf_counter()
    print(f"Pedigree layout suite — {len(names)} fixture(s)\n" + "=" * 68)

    for name in names:
        fixture = FIXTURES[name]
        trace = PedigreeTrace(f"fixture-{name}", write_to_disk=verbose)
        problems = []

        try:
            layout = compute_layout(fixture["individuals"], fixture["relationships"], trace)
            report = validate_layout(layout, fixture["individuals"], fixture["relationships"])
            svg = render_svg(layout, title=f"Pedigree — {name}")

            with open(os.path.join(OUT_DIR, f"{name}.svg"), "w", encoding="utf-8") as fh:
                fh.write(svg)

            problems = [str(issue) for issue in report.errors]
            problems += check_expectations(name, layout, report, fixture["expectations"])

            # Guard the escaping in the messy-input fixture rather than trusting it.
            if "<script>" in svg:
                problems.append("unescaped markup leaked into the SVG output")
            if not svg.startswith("<svg") or not svg.rstrip().endswith("</svg>"):
                problems.append("SVG output is malformed")

            status = "PASS" if not problems else "FAIL"
            detail = (f"{len(layout.nodes)} nodes, {len(layout.generations)} gens, "
                      f"{int(layout.width)}×{int(layout.height)}, "
                      f"fill {report.stats.get('fill_ratio', 0):.0%}, "
                      f"{report.stats.get('crossings', 0)} crossing(s)")
            print(f"  {status}  {name:<26} {detail}")

            if report.warnings and (verbose or problems):
                for issue in report.warnings:
                    print(f"           warn: {issue.message}")

        except Exception as exc:                                  # noqa: BLE001
            import traceback
            problems = [f"raised {type(exc).__name__}: {exc}"]
            print(f"  FAIL  {name:<26} {problems[0]}")
            if verbose:
                traceback.print_exc()

        if problems:
            failed.append((name, problems))
            for problem in problems:
                print(f"           → {problem}")
        else:
            passed.append(name)

    elapsed = (time.perf_counter() - started) * 1000
    print("=" * 68)
    print(f"{len(passed)} passed, {len(failed)} failed  ({elapsed:.0f} ms)")
    print(f"SVGs written to {OUT_DIR}/")

    if failed:
        print("\nFailures:")
        for name, problems in failed:
            print(f"  {name}")
            for problem in problems:
                print(f"    - {problem}")
        return 1
    return 0


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    flags = [a for a in sys.argv[1:] if a.startswith("-")]
    sys.exit(run(args[0] if args else None, verbose="-v" in flags or "--verbose" in flags))
