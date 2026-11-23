"""Offline checks for the vendored jcr_mcp database adapter."""
import sqlite3
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from research_verify.jcr_adapter import JCRDatabase, get_database, lookup_source


class JcrMcpAdapterTests(unittest.TestCase):
    def setUp(self):
        directory = self.enterContext(TemporaryDirectory())
        self.path = str(Path(directory) / "fixture.db")
        with sqlite3.connect(self.path) as db:
            db.executescript("""
                CREATE TABLE JCR2025 (Journal, IF);
                INSERT INTO JCR2025 VALUES ('Nature', '56.1'), ('Nature Medicine', '52.5');
                CREATE TABLE JCR2024 (Journal, IF);
                INSERT INTO JCR2024 VALUES ('Nature Medicine', '48.5');
                CREATE TABLE XR2026 (Journal);
                INSERT INTO XR2026 VALUES ('Nature Medicine');
            """)
        self.enterContext(patch('research_verify.jcr_adapter.get_database',
                                return_value=JCRDatabase(self.path)))

    def test_latest_uses_latest_numeric_jcr_if_not_xr_partition_year(self):
        row = lookup_source({"journal": "Nature Medicine"}, minimum=10, year="latest")
        self.assertEqual(row["status"], "found")
        self.assertEqual(row["metric_year"], 2025)
        self.assertEqual(row["impact_factor"], 52.5)
        self.assertTrue(row["passes_threshold"])
        self.assertEqual(row["metric_source"], "jcr_mcp ShowJCR JCR table")

    def test_abbreviated_journal_resolves_by_electronic_issn(self):
        with sqlite3.connect(self.path) as db:
            db.executescript("""
                ALTER TABLE JCR2025 ADD COLUMN EISSN;
                UPDATE JCR2025 SET EISSN='1546-170X' WHERE Journal='Nature Medicine';
            """)
        row = lookup_source({"journal": "Nat Med", "eissn": "1546-170x"})
        self.assertEqual(row["journal"], "Nature Medicine")
        self.assertEqual(row["journal_match"], "issn")
        self.assertEqual(row["impact_factor"], 52.5)

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


def test_catalog_survives_a_rebuild_in_the_data_volume(tmp_path, monkeypatch):
    monkeypatch.delenv("LDR_JCR_CATALOG_PATH", raising=False)
    monkeypatch.setenv("LDR_DATA_DIR", str(tmp_path))
    catalog = tmp_path / "journal_data" / "jcr.db"
    catalog.parent.mkdir()
    with sqlite3.connect(catalog) as db:
        db.executescript("CREATE TABLE JCR2025 (Journal, IF); INSERT INTO JCR2025 VALUES ('Test Journal', 23);")
    get_database.cache_clear()
    try:
        assert lookup_source({"journal": "Test Journal"})["impact_factor"] == 23
        assert get_database().read_only
        catalog.unlink()
        assert lookup_source({"journal": "Test Journal"})["status"] == "metric_unavailable"
        assert not catalog.exists()
    finally:
        get_database.cache_clear()


if __name__ == "__main__":
    unittest.main()
