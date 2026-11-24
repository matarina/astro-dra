"""Shared async HTTP client for ``research_verify`` external lookups.

Wraps ``httpx.AsyncClient`` with a bounded-concurrency semaphore, retries with
exponential backoff (transport errors only), and a typed :class:`HttpResult`
that lets callers distinguish:

* ``ok``               -> HTTP 2xx, payload available;
* ``not_found``        -> HTTP 404, the resource definitively does not exist;
* ``transport_error``  -> could not reach the network (offline / timeout / proxy).

The verification chain maps a transport error to ``unverified`` (leave a trace)
instead of treating it as a hard failure, honouring the "never block the main
flow" contract.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

import httpx
from loguru import logger

from .config import VerifyConfig


class EgressDenied(httpx.RequestError):
    """A verification request was refused before its transport ran."""


@dataclass
class HttpResult:
    """Outcome of a single GET request."""

    status: int | None
    json: Any | None
    text: str | None
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.status is not None and 200 <= self.status < 300

    @property
    def not_found(self) -> bool:
        return self.status == 404

    @property
    def transport_error(self) -> bool:
        return self.status is None and self.error is not None


class HttpClient:
    """Async HTTP helper. Use as an async context manager::

        async with HttpClient(config) as http:
            res = await http.get("https://api.crossref.org/works/10.../")
    """

    def __init__(
        self,
        config: VerifyConfig | None = None,
        *,
        client: httpx.AsyncClient | None = None,
        egress_context=None,
    ) -> None:
        self._config = config or VerifyConfig()
        self._sem = asyncio.Semaphore(max(1, self._config.http_concurrency))
        self._client = client
        self._owns_client = client is None
        self._egress_context = egress_context

    async def _check_egress(self, request: httpx.Request) -> None:
        from local_deep_research.security.egress.policy import evaluate_url

        decision = evaluate_url(str(request.url), self._egress_context)
        if not decision.allowed:
            raise EgressDenied(decision.reason, request=request)

    async def __aenter__(self) -> "HttpClient":
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=self._config.http_timeout,
                follow_redirects=True,
                headers={"User-Agent": "ldr-research-verify/0.1"},
                event_hooks={"request": [self._check_egress]} if self._egress_context is not None else None,
            )
        return self

    async def __aexit__(self, *exc: object) -> None:
        if self._owns_client and self._client is not None:
            await self._client.aclose()
            self._client = None

    async def get(
        self,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> HttpResult:
        """GET ``url`` with retries on transport errors only."""
        if self._client is None:
            raise RuntimeError("HttpClient must be used as an async context manager")

        attempts = max(1, self._config.http_max_retries + 1)
        async with self._sem:
            for attempt in range(1, attempts + 1):
                try:
                    resp = await self._client.get(url, params=params, headers=headers)
                except EgressDenied as exc:
                    return HttpResult(status=None, json=None, text=None, error=f"egress_denied:{exc}")
                except httpx.HTTPError as exc:  # timeout / connect / proxy errors
                    if attempt < attempts:
                        await asyncio.sleep(min(2 ** (attempt - 1), 4))
                        continue
                    logger.warning(
                        "research_verify http transport error url={} err={}", url, exc
                    )
                    return HttpResult(status=None, json=None, text=None, error=str(exc))

                data: Any | None = None
                ctype = resp.headers.get("content-type", "")
                if "json" in ctype:
                    try:
                        data = resp.json()
                    except ValueError:
                        data = None
                return HttpResult(status=resp.status_code, json=data, text=resp.text)

        # Unreachable: loop always returns, but keep a defensive fallback.
        return HttpResult(status=None, json=None, text=None, error="unreachable")
