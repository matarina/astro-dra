"""Tests for denominator integrity and matched report comparison."""
import copy
import unittest
from evidence_eval_metrics import evaluate, paired, _bootstrap


class MetricsTests(unittest.TestCase):
    def test_missing_claim_labels_not_successes(self):
        result=evaluate({'cases':[{'claims':[{'grounding':'unsupported'},{}]}]})
        self.assertEqual(result['unsupported_claim_rate']['rate'],1)
        self.assertEqual(result['grounding_missing_count'],1)
        self.assertIsNone(result['citation_entailment_rate']['rate'])

    def test_precision_is_not_recall(self):
        r=evaluate({'cases':[{'retrieval':{'PubMed':{'relevant_retrieved':2,'retrieved':4,'gold_relevant':10}}}]})['retrieval_by_engine']['PubMed']
        self.assertEqual(r['precision']['rate'],.5)
        self.assertEqual(r['recall']['rate'],.2)

    def test_no_gold_no_recall(self):
        r=evaluate({'cases':[{'retrieval':{'SearXNG':{'relevant_retrieved':2,'retrieved':4}}}]})['retrieval_by_engine']['SearXNG']
        self.assertIsNone(r['recall']['rate'])
        self.assertEqual(r['missing_gold_cases'],1)

    def test_bad_retrieval_counts_rejected(self):
        with self.assertRaises(ValueError):
            evaluate({'cases':[{'retrieval':{'EuropePMC':{'relevant_retrieved':3,'retrieved':2}}}]})

    def test_configuration_mismatch_excluded(self):
        case={'case_id':'a','domain':'biology','model':'m','temperature':0,'source_pack_sha256':'s','settings_sha256':'c','claims':[{'grounding':'supported'}]}
        b={'cases':[case]};c=copy.deepcopy(b);c['cases'][0]['model']='other'
        r=paired(b,c);self.assertEqual(r['matched_cases'],0);self.assertEqual(r['status'],'incomplete_pairing')

    def test_matched_delta_and_empty_independence(self):
        case={'case_id':'a','domain':'medicine','model':'m','temperature':0,'source_pack_sha256':'s','settings_sha256':'c','claims':[{'grounding':'unsupported'}]}
        b={'cases':[case]};c=copy.deepcopy(b);c['cases'][0]['claims'][0]['grounding']='supported'
        r=paired(b,c);self.assertEqual(r['matched_cases'],1)
        self.assertEqual(r['paired_report_deltas_by_domain']['medicine']['unsupported_claim_rate']['mean_delta'],-1)
        self.assertEqual(r['assessment_provenance']['baseline']['independence'],'unreported')
        self.assertIsNone(r['paired_report_deltas_by_domain']['all']['unsupported_claim_rate']['bootstrap95'])

    def test_no_data_not_pass(self):
        self.assertEqual(paired({'cases':[]},{'cases':[]})['status'],'incomplete_pairing')

    def test_paraphrases_do_not_count_as_independent_families(self):
        result = _bootstrap([0.1, 0.2, 0.3], ['same', 'same', 'same'])
        self.assertEqual(result['n'], 3)
        self.assertEqual(result['task_families'], 1)
        self.assertIsNone(result['bootstrap95'])


if __name__=='__main__':unittest.main()
