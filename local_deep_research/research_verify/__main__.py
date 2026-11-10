"""Self-test entry point: ``python -m research_verify``.

Prints the effective configuration and, if DOI validation is enabled, pings
Crossref for a known-real DOI.  A network failure is reported but *not* fatal,
mirroring the offline-degradation contract of the verification chain.
"""

from __future__ import annotations

import asyncio
import json

from .config import get_config
from .http_client import HttpClient

# A well-known, long-lived DOI (the NumPy paper) used only as a reachability probe.
SAMPLE_DOI = "10.1038/s41586-020-2649-2"


async def _ping_crossref() -> dict:
    cfg = get_config()
    url = f"https://api.crossref.org/works/{SAMPLE_DOI}"
    async with HttpClient(cfg) as http:
        res = await http.get(url, params={"mailto": cfg.crossref_mailto})
    return {"status": res.status, "ok": res.ok, "error": res.error}


def main() -> int:
    cfg = get_config()
    print("research_verify", __import__("research_verify").__version__)
    print("config:")
    print(json.dumps(cfg.model_dump(), indent=2, ensure_ascii=False))
    print("module_enabled(doi_validation) =", cfg.module_enabled("doi_validation"))

    if cfg.module_enabled("doi_validation"):
        try:
            print("crossref ping:", asyncio.run(_ping_crossref()))
        except Exception as exc:  # offline is acceptable here
            print("crossref ping skipped (offline?):", exc)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
