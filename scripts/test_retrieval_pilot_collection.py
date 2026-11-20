import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from collect_retrieval_pilot import collect


class RetrievalCollectionTests(unittest.TestCase):
    def setup_record(self, root, payload, failures=0):
        folder=root/'baseline';folder.mkdir()
        raw=json.dumps(payload).encode();(folder/'response.bin').write_bytes(raw)
        row={'case_id':'test','engine':'searxng','status':'completed','known_item_hit':False,'returned_count':0,'latency_seconds':1.,'transport_failures':failures,'sources':[],
             'requests':[{'file':'response.bin','sha256':hashlib.sha256(raw).hexdigest()}]}
        (folder/'case.json').write_text(json.dumps(row))

    def test_http_200_with_upstream_errors_is_not_literature_absence(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);self.setup_record(root,{'results':[],'unresponsive_engines':[['bing','HTTP connection error']]})
            stats=collect(root)['arms']['baseline']['searxng']
            self.assertEqual(stats['empty_with_upstream_failures'],1)
            self.assertEqual(stats['cases'][0]['effective_status'],'empty_with_upstream_failures')

    def test_changed_payload_rejected(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);self.setup_record(root,{'results':[]})
            (root/'baseline/response.bin').write_bytes(b'changed')
            with self.assertRaises(ValueError):collect(root)

    def test_transport_failure_is_preserved(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);self.setup_record(root,{},failures=1)
            stats=collect(root)['arms']['baseline']['searxng']
            self.assertEqual(stats['cases'][0]['effective_status'],'empty_with_transport_failures')


if __name__=='__main__':unittest.main()
