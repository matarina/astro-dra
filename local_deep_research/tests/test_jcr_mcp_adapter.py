"""Offline checks for the vendored jcr_mcp database adapter."""
import sqlite3
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from research_verify.jcr_adapter import JCRDatabase, lookup_source


class JcrMcpAdapterTests(unittest.TestCase):
    def setUp(self):
        directory = self.enterContext(TemporaryDirectory())
        path = str(Path(directory) / "fixture.db")
        with sqlite3.connect(path) as db:
            db.executescript("""
                CREATE TABLE JCR2025 (Journal, IF);
                INSERT INTO JCR2025 VALUES ('Nature', '56.1'), ('Nature Medicine', '52.5');
                CREATE TABLE JCR2024 (Journal, IF);
                INSERT INTO JCR2024 VALUES ('Nature Medicine', '48.5');
                CREATE TABLE XR2026 (Journal);
                INSERT INTO XR2026 VALUES ('Nature Medicine');
            """)
        self.enterContext(patch('research_verify.jcr_adapter.get_database',
                                return_value=JCRDatabase(path)))

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

    def test_ranking_lookup_needs_no_threshold(self):
        row = lookup_source({"journal": "Nature Medicine"})
        self.assertEqual(row["status"], "found")
        self.assertEqual(row["impact_factor"], 52.5)
        self.assertIsNone(row["passes_threshold"])

    def test_missing_journal_is_unknown(self):
        row = lookup_source({"journal": "No Such Journal"}, minimum=10)
        self.assertEqual(row["status"], "metric_unavailable")
        self.assertIsNone(row["passes_threshold"])


if __name__ == "__main__":
    unittest.main()
