"""Offline runtime check for isolated DRA experiments, never a quality verdict.

Run with the candidate image's Python and the workspace mounted read-only.
No credentials or model endpoint are needed. --load-workspace-handlers loads
only the two citation handler overlays into this probe process, without
changing installed files. It demonstrates the effect of the missing overlay.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib
import importlib.util
import inspect
import json
from pathlib import Path
from types import SimpleNamespace


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_handlers(root):
    for short in ("base_citation_handler", "standard_citation_handler"):
        name = f"local_deep_research.citation_handlers.{short}"
        path = root / "local_deep_research/overlay" / f"{short}.py"
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        import sys
        sys.modules[name] = module
        spec.loader.exec_module(module)


class NoNetworkEvidence:
    def pmc_identifiers(self, *args, **kwargs):
        return {}

    def article(self, *args, **kwargs):
        return ""

    def web(self, *args, **kwargs):
        return []


class ProbeModel:
    def __init__(self):
        self.prompts = []

    def invoke(self, prompt, *args, **kwargs):
        prompt = str(prompt)
        self.prompts.append(prompt)
        if prompt.startswith("Rank supplied passages"):
            indices = [int(line.split()[1]) for line in prompt.splitlines()
                       if line.startswith("PASSAGE ")]
            return SimpleNamespace(content=json.dumps({"rankings": [
                {"index": i, "score": float(i)} for i in indices]}))
        return SimpleNamespace(content="The supplied study describes an association [8].")


class ProbeRanker:
    def __init__(self, model):
        from research_verify.semantic_reranker import LLMPassageRanker
        self.inner = LLMPassageRanker(model.invoke)
        self.calls = 0

    def rank(self, query, passages):
        self.calls += 1
        return self.inner.rank(query, passages)


def run_probe(root, load_workspace=False):
    if load_workspace:
        load_handlers(root)
    from local_deep_research.citation_handler import CitationHandler
    from local_deep_research.citation_handlers.standard_citation_handler import StandardCitationHandler
    from local_deep_research.citation_handlers.base_citation_handler import BaseCitationHandler
    files = {}
    for label, cls in (("standard", StandardCitationHandler), ("base", BaseCitationHandler)):
        actual = Path(inspect.getfile(cls))
        expected = root / "local_deep_research/overlay" / f"{label}_citation_handler.py"
        files[label] = {"loaded_path": str(actual), "loaded_sha256": digest(actual),
                        "expected_sha256": digest(expected), "matches_workspace": digest(actual) == digest(expected)}
    model = ProbeModel()
    settings = {"general.enable_fact_checking": False, "citation.enable_source_reading": False,
                "citation.semantic_passage_ranking": True, "citation.source_context_chars": 4500}
    wrapper = CitationHandler(model, handler_type="standard", settings_snapshot=settings)
    handler = wrapper._handler
    handler.evidence_fetcher = NoNetworkEvidence()
    ranker = ProbeRanker(model)
    handler.semantic_passage_ranker = ranker
    sources = [{"index": i, "title": f"Synthetic routing probe {i}",
                "link": f"https://example.invalid/study/{i}",
                "abstract": f"Marker {i}. " + "An observed association does not establish causality. " * 22}
               for i in range(1, 9)]
    result = wrapper.analyze_followup("Which study describes an association?", sources, "", 0)
    writer_prompts = [p for p in model.prompts if "Previous Knowledge:" in p]
    return {"files": files, "process_only_handler_overlay": load_workspace,
            "source_chars": sum(len(s["abstract"]) for s in sources),
            "requested_source_budget": 4500, "ranker_calls": ranker.calls,
            "model_stub_calls": len(model.prompts),
            "writer_has_reading_limits": any("EVIDENCE READING LIMITS" in p for p in writer_prompts),
            "writer_prompt_chars": [len(p) for p in writer_prompts],
            "returned_documents": [int(d.metadata["index"]) for d in result.get("documents", [])],
            "report_nonempty": bool(result.get("content")),
            "runtime_route_confirmed": ranker.calls > 0 and all(v["matches_workspace"] for v in files.values()),
            "external_model_calls": 0, "scientific_accuracy_evaluated": False,
            "limitations": "Synthetic routing only; stub relevance scores and answers do not establish ranking quality or hallucination reduction."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, default=Path("/workspace"))
    parser.add_argument("--load-workspace-handlers", action="store_true")
    args = parser.parse_args()
    print(json.dumps(run_probe(args.workspace, args.load_workspace_handlers), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
