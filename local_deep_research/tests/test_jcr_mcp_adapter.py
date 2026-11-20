"""Offline checks for the vendored jcr_mcp database adapter."""
import unittest

from research_verify.jcr_adapter import lookup_source


class JcrMcpAdapterTests(unittest.TestCase):
    def test_latest_uses_latest_numeric_jcr_if_not_xr_partition_year(self):
        row = lookup_source({"journal": "Nature Medicine"}, minimum=10, year="latest")
        self.assertEqual(row["status"], "found")
        self.assertEqual(row["metric_year"], 2025)
        self.assertEqual(row["impact_factor"], 52.5)
        self.assertTrue(row["passes_threshold"])
        self.assertEqual(row["metric_source"], "jcr_mcp ShowJCR JCR table")

    def test_threshold_operator_is_structured(self):
        row = lookup_source({"journal": "Nature"}, minimum=56.1, operator=">", year=2025)
        self.assertEqual(row["status"], "found")
        self.assertFalse(row["passes_threshold"])

    def test_missing_journal_is_unknown(self):
        row = lookup_source({"journal": "No Such Journal"}, minimum=10)
        self.assertEqual(row["status"], "metric_unavailable")
        self.assertIsNone(row["passes_threshold"])


if __name__ == "__main__":
    unittest.main()
