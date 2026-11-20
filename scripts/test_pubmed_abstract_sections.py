"""Parser contracts for nested text, section order and distinct translations."""
from pathlib import Path
import unittest
from check_pubmed_abstract_integrity import parse_with_module


MODULE = Path(__file__).resolve().parents[1] / "local_deep_research/search_engine_pubmed.py"


def parse(xml):
    return parse_with_module(MODULE,xml,["1"])


class AbstractSectionTests(unittest.TestCase):
    def test_single_primary_section_is_not_duplicated(self):
        xml = '<PubmedArticleSet><PubmedArticle><MedlineCitation><PMID>1</PMID><Article><Abstract><AbstractText>One result.</AbstractText></Abstract></Article></MedlineCitation></PubmedArticle></PubmedArticleSet>'
        self.assertEqual(parse(xml),{"1":"One result."})

    def test_nested_markup_and_tails_preserved_in_source_order(self):
        xml = '<PubmedArticleSet><PubmedArticle><MedlineCitation><PMID>1</PMID><Article><Abstract><AbstractText Label="RESULTS"><i>TP53</i> change P&lt;0.01; unit m<sup>2</sup> remains.</AbstractText><AbstractText Label="LIMITS">Only this cohort.</AbstractText></Abstract></Article></MedlineCitation></PubmedArticle></PubmedArticleSet>'
        self.assertEqual(parse(xml)["1"],"RESULTS: TP53 change P<0.01; unit m [superscript:2] remains.\n\nLIMITS: Only this cohort.")

    def test_other_abstract_does_not_merge_into_primary_version(self):
        xml = '<PubmedArticleSet><PubmedArticle><MedlineCitation><PMID>1</PMID><Article><Abstract><AbstractText>Primary.</AbstractText></Abstract></Article><OtherAbstract Language="fre"><AbstractText>Separate translation.</AbstractText></OtherAbstract></MedlineCitation></PubmedArticle></PubmedArticleSet>'
        self.assertEqual(parse(xml),{"1":"Primary."})


if __name__ == "__main__": unittest.main()
