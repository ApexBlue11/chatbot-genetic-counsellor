"""
Regression tests for variant identifier parsing and frequency extraction.

Both of these failed silently in production. The router could not handle the
gene-in-parentheses HGVS that ClinVar itself displays, so every database was
queried with None; and nothing ever read the gnomAD frequencies out of the
MyVariant/VEP payloads, so the tool reported no frequency data for variants
where both APIs had it. In each case the model filled the gap from memory and
presented the result as a database lookup.

Uses recorded payload shapes, so it runs offline.

    python tests/test_variant_parsing.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from analysis.variant_analyser import VariantAnalyzer          # noqa: E402
from core.query_router import GenomicQueryRouter               # noqa: E402

failures = []


def check(name, condition, extra=""):
    print(f"  {'PASS' if condition else 'FAIL'}  {name}{'  ' + extra if extra else ''}")
    if not condition:
        failures.append(name)


def test_routing():
    router = GenomicQueryRouter()
    cases = [
        # The form ClinVar displays — this is what silently resolved to None.
        ("NM_000492.4(CFTR):c.1521_1523delCTT", "hgvs_transcript", "NM_000492.4:c.1521_1523delCTT"),
        ("NM_000518.5(HBB):c.20A>T", "hgvs_transcript", "NM_000518.5:c.20A>T"),
        ("NP_000509.1(HBB):p.Glu7Val", "hgvs_protein", "NP_000509.1:p.Glu7Val"),
        ("NM_000492.4:c.1521_1523delCTT", "hgvs_transcript", "NM_000492.4:c.1521_1523delCTT"),
        ("rs334", "rsid", "rs334"),
        ("BRCA1", "gene_symbol", "BRCA1"),
        ("What does NM_000492.4(CFTR):c.1521_1523delCTT mean?", "hgvs_transcript",
         "NM_000492.4:c.1521_1523delCTT"),
    ]
    for query, want_type, want_id in cases:
        got = router.classify(query)
        check(f"routes {query[:42]!r}",
              got.query_type == want_type and got.extracted_identifier == want_id,
              f"got {got.query_type}/{got.extracted_identifier!r}")

    check("no identifier is silently None for a real variant",
          all(router.classify(q).extracted_identifier for q, _, _ in cases))


def test_frequency_from_myvariant():
    """MyVariant nests gnomAD under gnomad_exome.af.*"""
    analyzer = VariantAnalyzer()
    payload = {"gnomad_exome": {"af": {
        "af": 0.00706849, "af_nfe": 0.0122683, "af_afr": 0.00295421, "af_eas": 0.0,
    }}}
    freq = analyzer._extract_population_frequency(payload, [])
    check("MyVariant global frequency extracted",
          abs(freq.get("global", {}).get("percent", 0) - 0.7068) < 0.001,
          str(freq.get("global")))
    check("ancestry groups are labelled, not raw codes",
          "European (non-Finnish)" in freq and "African/African-American" in freq)
    check("a genuine zero frequency is kept, not dropped as falsy",
          freq.get("East Asian", {}).get("allele_frequency") == 0.0)
    check("every entry names its source",
          all("gnomAD" in v["source"] for v in freq.values()))


def test_frequency_from_vep_fallback():
    """VEP nests them under colocated_variants[].frequencies.<alt>.*"""
    analyzer = VariantAnalyzer()
    vep = [{"colocated_variants": [{"frequencies": {"T": {
        "gnomade": 0.01235, "gnomade_nfe": 0.01498, "gnomade_fin": 0.002757,
    }}}]}]
    freq = analyzer._extract_population_frequency({}, vep)
    check("VEP fallback yields frequencies when MyVariant has none",
          "global" in freq and "European (non-Finnish)" in freq,
          f"{len(freq)} populations")
    check("VEP source is attributed to VEP",
          "VEP" in freq.get("global", {}).get("source", ""))


def test_absent_means_absent():
    analyzer = VariantAnalyzer()
    check("no data yields an empty dict, not invented numbers",
          analyzer._extract_population_frequency({}, []) == {})


def main():
    print(f"Variant parsing and frequency extraction\n{'=' * 66}")
    test_routing()
    test_frequency_from_myvariant()
    test_frequency_from_vep_fallback()
    test_absent_means_absent()
    print("=" * 66)
    print("all checks passed" if not failures else f"{len(failures)} failed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
