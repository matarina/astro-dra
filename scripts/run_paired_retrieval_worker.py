"""Run native previews on a frozen query schedule inside a disposable container."""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import sys
import time
from urllib.parse import parse_qs, urlsplit


def main():
    from loguru import logger
    import requests
    from local_deep_research.web_search_engines.engines.search_engine_europepmc import EuropePMCSearchEngine
    from local_deep_research.web_search_engines.engines.search_engine_pubmed import PubMedSearchEngine
    from local_deep_research.web_search_engines.engines.search_engine_searxng import SearXNGSearchEngine

    logger.remove()
    root = Path("/experiment")
    protocol = json.loads((root / "retrieval-protocol.json").read_text())
    cases = {row["case_id"]: row for row in json.loads((root / "cases.json").read_text())
             if row["variant"] in protocol["variants"]}
    arm = os.environ["PILOT_ARM"]
    output = root / "retrieval" / arm
    output.mkdir(parents=True, exist_ok=True)
    requests_seen = []
    original_send = requests.sessions.Session.send
    public_hosts = {"eutils.ncbi.nlm.nih.gov", "www.ebi.ac.uk"}
    quota = root / "transport-quota"
    quota.mkdir(exist_ok=True)

    def capture(session, request, **kwargs):
        url = urlsplit(request.url)
        params = {key: value for key, value in parse_qs(url.query).items()
                  if key in {"q", "query", "term", "retmax", "pageSize", "id", "format", "engines"}}
        event = {"host": url.hostname, "path": url.path, "params": params}
        ordinal = len(requests_seen)
        requests_seen.append(event)
        if url.hostname in public_hosts:
            with (quota / url.hostname).open("a+") as lock:
                fcntl.flock(lock, fcntl.LOCK_EX)
                lock.seek(0)
                previous = float(lock.read() or "0")
                time.sleep(max(0, previous + protocol["public_request_gap_seconds"] - time.monotonic()))
                lock.seek(0)
                lock.truncate()
                lock.write(str(time.monotonic()))
                lock.flush()
        start = time.monotonic()
        try:
            if kwargs.get("timeout") is None:
                kwargs["timeout"] = (8, 30)
            response = original_send(session, request, **kwargs)
            relative = "response-" + str(ordinal) + ".bin"
            (output / relative).write_bytes(response.content)
            event.update(status_code=response.status_code, file=relative,
                         sha256=hashlib.sha256(response.content).hexdigest())
            return response
        except Exception as error:
            event["error_type"] = type(error).__name__
            raise
        finally:
            event["latency_seconds"] = time.monotonic() - start

    requests.sessions.Session.send = capture
    print("READY", flush=True)
    for line in sys.stdin:
        task = json.loads(line)
        case = cases[task["case_id"]]
        engine = task["engine"]
        if engine not in protocol["engines"]:
            raise ValueError("Unexpected engine")
        destination = output / (engine + "-" + case["case_id"] + ".json")
        if destination.exists():
            raise ValueError("Existing retrieval observation")
        before = len(requests_seen)
        start = time.monotonic()
        row = {"arm": arm, "engine": engine, "case_id": case["case_id"], "family": case["family"],
               "variant": case["variant"], "domain": case["domain"], "query": case["retrieval_query"],
               "started_unix": time.time(), "requested_budget": protocol["preview_budget"]}
        obj = None
        try:
            settings = {"max_results": protocol["preview_budget"], "llm": None}
            if engine == "pubmed":
                obj = PubMedSearchEngine(**settings, optimize_queries=False, get_full_text=False)
            elif engine == "europepmc":
                obj = EuropePMCSearchEngine(**settings, programmatic_mode=True)
            else:
                obj = SearXNGSearchEngine(**settings, instance_url=protocol["searxng_instance"],
                                          result_format="json", include_full_content=False,
                                          programmatic_mode=True)
            row["effective_budget"] = obj.max_results
            sources = obj._get_previews(row["query"])
            row.update(status="returned", sources=sources, returned=len(sources))
        except Exception as error:
            row.update(status="raised", error_type=type(error).__name__)
        finally:
            if obj is not None and hasattr(obj, "close"):
                try:
                    obj.close()
                except Exception as error:
                    row["close_error_type"] = type(error).__name__
        row.update(requests=requests_seen[before:], latency_seconds=time.monotonic() - start)
        destination.write_text(json.dumps(row, ensure_ascii=False, indent=2, default=str) + "\n")
        print("DONE " + case["case_id"] + " " + engine, flush=True)


if __name__ == "__main__":
    main()
