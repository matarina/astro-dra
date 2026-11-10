"""Probe the three search services without a model call or creating research.

Run inside the application container so its proxy, DNS and network are exercised:
docker exec -i CONTAINER /install/.venv/bin/python - < scripts/check_search_connectivity.py
"""

import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import time

import requests


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--query", default="cancer")
    parser.add_argument("--searxng-url", default="http://searxng:8080")
    parser.add_argument("--timeout", type=float, default=18)
    args = parser.parse_args()
    services = [
        ("pubmed", "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi",
         {"db": "pubmed", "term": args.query, "retmode": "json", "retmax": 3}),
        ("europepmc", "https://www.ebi.ac.uk/europepmc/webservices/rest/search",
         {"query": args.query, "format": "json", "pageSize": 3}),
        ("searxng", args.searxng_url.rstrip("/") + "/search",
         {"q": args.query, "format": "json"}),
    ]

    def probe(service):
        name, url, params = service
        started = time.monotonic()
        result = {"engine": name, "ok": False}
        try:
            response = requests.get(url, params=params, timeout=args.timeout)
            result["http_status"] = response.status_code
            response.raise_for_status()
            data = response.json()
            if name == "pubmed":
                rows = data.get("esearchresult", {}).get("idlist", [])
            elif name == "europepmc":
                rows = data.get("resultList", {}).get("result", [])
            else:
                rows = data.get("results", [])
                result["unresponsive_engines"] = data.get("unresponsive_engines", [])
            result.update(returned=len(rows), ok=bool(rows))
        except (requests.RequestException, ValueError, TypeError, AttributeError) as error:
            # Exception strings may contain proxy URLs or credentials. Log only the type.
            result["error_type"] = type(error).__name__
        result["seconds"] = round(time.monotonic() - started, 2)
        return result

    with ThreadPoolExecutor(max_workers=3) as pool:
        results = list(pool.map(probe, services))
    print(json.dumps(results, ensure_ascii=False, indent=2))
    return 0 if all(result["ok"] for result in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
