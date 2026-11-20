"""Regression for literal scientific comparisons swallowed by tag regexes."""
import unittest
from normalize_abstract_markup import abstract_text


class AbstractMarkupTests(unittest.TestCase):
    def test_comparison_does_not_erase_following_results(self):
        raw = "<p>Results: P<0.001. Subgroup ratio 0.64; CI 0.51 to 0.81.</p><p>Conclusion.</p>"
        text = abstract_text(raw)
        self.assertIn("P<0.001. Subgroup ratio 0.64; CI 0.51 to 0.81.", text)
        self.assertIn("Conclusion.", text)

    def test_nested_text_and_tails_remain(self):
        self.assertEqual(abstract_text("<p>Before <i>inside</i> after.</p>").strip(), "Before inside after.")

    def test_entity_and_literal_comparisons_both_survive(self):
        text = abstract_text("<p>P&lt;0.01 and x>2; y<4.</p>")
        self.assertIn("P<0.01 and x>2; y<4.", text)


if __name__ == "__main__": unittest.main()
