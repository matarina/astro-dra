"""Scope preservation checks for native PubMed adaptive retrieval."""
import ast
from pathlib import Path
from types import SimpleNamespace
import unittest
from typing import List, Tuple


ROOT=Path(__file__).resolve().parents[1]


def adaptive_method():
    tree=ast.parse((ROOT/'local_deep_research/search_engine_pubmed.py').read_text())
    cls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='PubMedSearchEngine')
    method=next(n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name=='_adaptive_search')
    ns={'Tuple':Tuple,'List':List}
    exec(compile(ast.Module(body=[method],type_ignores=[]),'native_adaptive','exec'),ns)
    return ns['_adaptive_search']


class PubMedScopeTests(unittest.TestCase):
    def test_general_query_does_not_gain_implicit_dates(self):
        sent=[]
        obj=SimpleNamespace(_search_pubmed=lambda q:sent.append(q) or ['old','new'])
        result=adaptive_method()(obj,'mechanisms of signaling')
        self.assertEqual(sent,['mechanisms of signaling'])
        self.assertEqual(result,(['old','new'],'requested_scope'))

    def test_explicit_query_survives_empty_response(self):
        sent=[];obj=SimpleNamespace(_search_pubmed=lambda q:sent.append(q) or [])
        q='molecular evolution AND ("2010/01/01"[dp] : "2018/12/31"[dp])'
        self.assertEqual(adaptive_method()(obj,q),([], 'requested_scope'))
        self.assertEqual(sent,[q])

    def test_no_volume_or_intent_classifier_invoked(self):
        def reject(*a):raise AssertionError('No semantic inference allowed')
        obj=SimpleNamespace(_search_pubmed=lambda q:['retained'],_get_result_count=reject,_is_historical_focused=reject)
        self.assertEqual(adaptive_method()(obj,'recent advances')[0],['retained'])


if __name__=='__main__':unittest.main()
