"""Denominator/source-localization regressions, not scientific assessment tests."""
import unittest
from assess_benchmark_reports import validate_claims
from collect_benchmark_reports import answer_strings


class AnnotationBoundaries(unittest.TestCase):
    def test_invalid_claim_remains_in_missing_denominator_without_losing_valid_sibling(self):
        good={"text":"A changed.","grounding":"supported","citations":[1],"citation_entails":True,
              "evidence":[{"source_id":1,"quote":"A changed."}]}
        valid,invalid=validate_claims({"claims":[good,{"text":"Invented draft phrase","grounding":"supported"}]},
            "A changed. [1]",[{"index":1,"abstract":"A changed."}])
        self.assertEqual((len(valid),len(invalid)),(1,1))
        self.assertEqual(valid[0]["raw_grounding"],"supported")

    def test_quote_presence_preserves_raw_label_but_cannot_validate_wrong_source_or_boolean_id(self):
        for source_id in [2,True]:
            claim={"text":"A changed.","grounding":"supported","citations":[1],"citation_entails":True,
                "evidence":[{"source_id":source_id,"quote":"A changed."}]}
            valid,invalid=validate_claims({"claims":[claim]},"A changed.",[{"index":1,"abstract":"A changed."}])
            self.assertFalse(invalid)
            self.assertEqual(valid[0]["raw_grounding"],"supported")
            self.assertEqual(valid[0]["quote_checked_grounding"],"unverifiable")
            self.assertIsNone(valid[0]["citation_entails"])

    def test_reference_quotes_cannot_be_localized_against_worker_ids_or_questions(self):
        strings=answer_strings({"question":"Question text", "answers":[{"worker_id":"worker-123",
            "answer":{"free_form_answer":"No extra parameters.","extractive_spans":[],"yes_no":False,
                      "evidence":["Evidence paragraph"]}}]})
        self.assertEqual(strings,["No extra parameters.","no"])


if __name__=="__main__":
    unittest.main()
