"""Assessment quote/type/cluster contracts; no scientific-label validation."""
import unittest

from assess_fulltext_budget import validate
from collect_fulltext_budget import interval


class AssessmentContracts(unittest.TestCase):
    def claim(self, **changes):
        return {"text": "A reported result [1].", "grounding": "supported", "citations": [1],
                "citation_entails": True, "evidence": [{"source_id": 1, "quote": "Actual source result."}], **changes}

    def check_claim(self, claim):
        return validate({"empirical_claims": [claim], "nonempirical_units": []},
                        "A reported result [1].", [{"index": 1, "full_content": "Body text.", "abstract": "Actual source result."}])

    def test_provided_abstract_remains_valid_when_body_also_exists(self):
        claims, invalid, _ = self.check_claim(self.claim())
        self.assertFalse(invalid)
        self.assertTrue(claims[0]["source_quotes_localized"])

    def test_fabricated_quote_cannot_certify_grounding_or_entailment(self):
        claims, _, _ = self.check_claim(self.claim(evidence=[{"source_id": 1, "quote": "Invented result."}]))
        self.assertEqual(claims[0]["grounding"], "supported")  # raw judgment retained
        self.assertEqual(claims[0]["quote_checked_grounding"], "unverifiable")
        self.assertIsNone(claims[0]["citation_entails"])

    def test_boolean_source_id_cannot_alias_integer_one(self):
        claims, _, _ = self.check_claim(self.claim(evidence=[{"source_id": True, "quote": "Actual source result."}]))
        self.assertFalse(claims[0]["source_quotes_localized"])

    def test_nonlocalizable_draft_span_is_retained_as_invalid(self):
        claims, invalid, _ = self.check_claim(self.claim(text="Paraphrased draft result."))
        self.assertFalse(claims)
        self.assertEqual(len(invalid), 1)

    def test_variants_do_not_reweight_family_mean(self):
        result = interval([("a", 0), ("a", 0), ("a", 0), ("b", 1)])
        self.assertEqual(result["family_count"], 2)
        self.assertEqual(result["paired_observations"], 4)
        self.assertEqual(result["mean_paired_family_delta_candidate_minus_baseline"], .5)


if __name__ == "__main__":
    unittest.main()
