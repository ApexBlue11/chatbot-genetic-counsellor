"""Regression tests for the ClinVar significance-string handling.

Every bug covered here came from the same trap: "pathogenic" is a substring of
"pathogenicity", so ClinVar's very common "Conflicting interpretations of
pathogenicity" read as a pathogenic call. It reached both the single-variant
classifier and the VCF prioritiser, and in both places it silently promoted an
unsettled variant to the most alarming category the UI has.

These are pure-logic tests on purpose — no network — so they stay meaningful
when the upstream databases are slow or unreachable.
"""
import sys
import unittest

sys.path.append('.')

from analysis.variant_analyser import VariantAnalyzer
from analysis.vcf_prioritizer import VCFPrioritizer

CATEGORIES = ["dangerous", "possibly_harmful", "vus", "unannotated", "benign"]

# Both spellings occur in live ClinVar: the wording changed, the old records did not.
CONFLICTING = [
    "Conflicting interpretations of pathogenicity",
    "Conflicting classifications of pathogenicity",
]


class TestVcfCategorisation(unittest.TestCase):
    def setUp(self):
        # __init__ pulls in API clients this test has no use for.
        self.prioritizer = VCFPrioritizer.__new__(VCFPrioritizer)

    def categorise(self, sig, impact="LOW", sift="", polyphen=""):
        buckets = {k: [] for k in CATEGORIES}
        self.prioritizer._categorize(
            {"clinical_sig": sig, "impact": impact, "sift": sift, "polyphen": polyphen},
            buckets,
        )
        found = [k for k in CATEGORIES if buckets[k]]
        self.assertEqual(len(found), 1, f"{sig!r} landed in {found}")
        return found[0]

    def test_conflicting_is_not_pathogenic(self):
        for sig in CONFLICTING:
            self.assertEqual(self.categorise(sig), "possibly_harmful", sig)

    def test_genuine_pathogenic_calls_still_rank_dangerous(self):
        for sig in ("Pathogenic", "Likely pathogenic", "Pathogenic/Likely pathogenic"):
            self.assertEqual(self.categorise(sig), "dangerous", sig)

    def test_benign_and_uncertain_keep_their_buckets(self):
        self.assertEqual(self.categorise("Benign"), "benign")
        self.assertEqual(self.categorise("Benign/Likely benign"), "benign")
        self.assertEqual(self.categorise("Uncertain significance"), "vus")

    def test_high_vep_impact_still_promotes_an_unannotated_variant(self):
        # This is the path that puts a variant in Dangerous with a blank
        # clinical significance — the table now shows the Impact column so the
        # reason is visible, but the rule itself must stay.
        self.assertEqual(self.categorise("", impact="HIGH"), "dangerous")
        self.assertEqual(self.categorise("", impact="LOW"), "unannotated")


class TestPathogenicityPrediction(unittest.TestCase):
    def setUp(self):
        self.analyzer = VariantAnalyzer()

    def predict(self, aggregate=None, review="", rcv_sigs=None):
        myvariant = {}
        if rcv_sigs is not None:
            myvariant = {"clinvar": {"rcv": [{"clinical_significance": s} for s in rcv_sigs]}}
        clinvar = {"clinical_significance": aggregate, "review_status": review} if aggregate else {}
        return self.analyzer._predict_pathogenicity(myvariant, [], clinvar)

    def test_conflicting_aggregate_scores_as_uncertain(self):
        for sig in CONFLICTING:
            result = self.predict(aggregate=sig)
            self.assertEqual(result["score"], 0.5, sig)

    def test_pathogenic_and_benign_aggregates_score_at_the_poles(self):
        self.assertEqual(self.predict(aggregate="Pathogenic")["score"], 1.0)
        self.assertEqual(self.predict(aggregate="Likely pathogenic")["score"], 0.9)
        self.assertEqual(self.predict(aggregate="Benign")["score"], 0.0)
        self.assertEqual(self.predict(aggregate="Likely benign")["score"], 0.1)

    def test_aggregate_wins_over_the_submission_pile(self):
        # ClinVar's reviewed consensus for MTHFR c.665C>T is Benign; a scan of
        # the individual submissions used to let one "...of pathogenicity"
        # record override it outright.
        result = self.predict(
            aggregate="Benign",
            review="criteria provided, multiple submitters, no conflicts",
            rcv_sigs=["Uncertain significance", CONFLICTING[0], "Benign"],
        )
        self.assertEqual(result["classification"], "Benign")
        self.assertEqual(result["score"], 0.0)
        self.assertIn("no conflicts", result["confidence"])

    def test_submission_fallback_reports_the_majority_not_the_first_scare(self):
        # With no aggregate available, the submissions are all there is — but a
        # single outlier must not speak for the rest, and the confidence must
        # not claim ClinVar's reviewed "High".
        result = self.predict(
            rcv_sigs=["Benign", "Benign", "Benign", CONFLICTING[0]],
        )
        self.assertEqual(result["classification"], "Benign")
        self.assertNotIn("High", result["confidence"])


if __name__ == "__main__":
    unittest.main()
