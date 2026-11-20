"""Replay only the writer against a completed prompt-03 source snapshot."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from types import SimpleNamespace


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--sources", type=Path, required=True)
    p.add_argument("--question", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    from local_deep_research.config.llm_config import get_llm
    from local_deep_research.citation_handlers.standard_citation_handler import StandardCitationHandler
    from local_deep_research.config.thread_settings import settings_context
    from local_deep_research.settings.manager import apply_environment_overrides_to_snapshot
    import local_deep_research

    defaults = Path(local_deep_research.__file__).parent / "defaults/default_settings.json"
    snapshot = apply_environment_overrides_to_snapshot(
        {k: v.get("value") for k, v in json.loads(defaults.read_text()).items()}
    )
    snapshot.update({
        "llm.provider": "openai_endpoint",
        "llm.model": "deepseek-v4.1-flash-gsq-rco-iq2_xxs",
        "llm.openai_endpoint.url": "http://127.0.0.1:8080/v1",
        "general.enable_fact_checking": False,
    })
    question = args.question.read_text()
    sources = json.loads(args.sources.read_text())
    with settings_context(SimpleNamespace(username=None, get_setting=lambda k, d=None: snapshot.get(k, d))):
        model = get_llm(settings_snapshot=snapshot)
        handler = StandardCitationHandler(model, settings_snapshot=snapshot)
        result = handler.analyze_followup(question, sources, "", 0)
    body = result.get("content", result.get("response", "")) if isinstance(result, dict) else str(result)
    args.output.write_text(body)
    print(json.dumps({"output": str(args.output), "chars": len(body), "sources": len(sources)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
