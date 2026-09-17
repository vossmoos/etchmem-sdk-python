"""Asynchronous client for the etchmem-server REST API."""
from __future__ import annotations

import os
from typing import Any

import httpx

from etchmem.client import DEFAULT_BASE_URL, DEFAULT_TIMEOUT
from etchmem.errors import ConnectionError, error_for_status
from etchmem.models import (
    ExportResult, Health, History, RecallResponse, RememberResult,
    SleepResult, Stats,
)


class AsyncEtchMem:
    """Asynchronous etchmem client (same surface as :class:`etchmem.EtchMem`).

    Usage::

        from etchmem import AsyncEtchMem

        async with AsyncEtchMem("http://localhost:8000") as mem:
            await mem.remember("Acme signed the Q3 renewal at $40k.",
                               source="agent-33", scope="sales")
            hits = await mem.recall("what did Acme sign?")

    Configuration falls back to environment variables:
    ``ETCHMEM_BASE_URL`` and ``ETCHMEM_API_KEY``.
    """

    def __init__(
        self,
        base_url: str | None = None,
        *,
        api_key: str | None = None,
        timeout: float = DEFAULT_TIMEOUT,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.base_url = (base_url
                         or os.environ.get("ETCHMEM_BASE_URL")
                         or DEFAULT_BASE_URL).rstrip("/")
        self.api_key = api_key or os.environ.get("ETCHMEM_API_KEY")
        headers = {"Accept": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        self._client = client or httpx.AsyncClient(
            base_url=self.base_url, timeout=timeout)
        self._client.headers.update(headers)

    # ── lifecycle ──────────────────────────────────────────────────────

    async def close(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> "AsyncEtchMem":
        return self

    async def __aexit__(self, *exc: Any) -> None:
        await self.close()

    # ── internal ───────────────────────────────────────────────────────

    async def _request(self, method: str, path: str,
                       json: dict[str, Any] | None = None,
                       params: dict[str, Any] | None = None) -> dict[str, Any]:
        try:
            resp = await self._client.request(method, path, json=json, params=params)
        except httpx.HTTPError as e:
            raise ConnectionError(
                f"etchmem server unreachable at {self.base_url}: {e}") from e
        if resp.status_code >= 400:
            try:
                detail = resp.json().get("detail", resp.text)
            except Exception:
                detail = resp.text
            raise error_for_status(resp.status_code, detail)
        return resp.json()

    # ── API surface ────────────────────────────────────────────────────

    async def remember(
        self,
        data: str,
        *,
        source: str,
        scope: str,
        extract_mode: str = "deferred",
        metadata: dict[str, Any] | None = None,
        occurred_at: str | float | None = None,
    ) -> RememberResult:
        """Deposit a raw text signal (see :meth:`etchmem.EtchMem.remember`)."""
        payload = await self._request("POST", "/remember", json={
            "data": data, "source": source, "scope": scope,
            "extract_mode": extract_mode, "metadata": metadata or {},
            "occurred_at": occurred_at})
        return RememberResult.from_dict(payload)

    async def recall(
        self,
        query: str,
        *,
        scope: str | None = None,
        source: str | None = None,
        top_k: int = 5,
        include_signals: bool = True,
        as_of: str | None = None,
        as_of_basis: str = "ingest",
    ) -> RecallResponse:
        """Semantic recall over etches; ``as_of`` enables time-travel."""
        payload = await self._request("POST", "/recall", json={
            "query": query, "scope": scope, "source": source, "top_k": top_k,
            "include_signals": include_signals, "as_of": as_of,
            "as_of_basis": as_of_basis})
        return RecallResponse.from_dict(payload)




    async def associate(
        self,
        query: str,
        *,
        scope: str | None = None,
        top_k: int = 5,
        hops: int = 1,
        as_of: str | None = None,
        min_score: float = 0.15,
        as_of_basis: str = "ingest",
    ) -> Association:
        """What the memory holds for a phrase.

        Use when you do NOT already know which entity you are asking about.
        :meth:`recall` ranks beliefs by wording; this also returns every fact
        about each matched subject and follows declared relations one hop, so a
        fault reached by wording leads to the part that fixes it — which
        wording alone never would.
        """
        payload = await self._request("POST", "/associate", json={
            "query": query, "scope": scope, "top_k": top_k, "hops": hops,
            "as_of": as_of, "min_score": min_score,
            "as_of_basis": as_of_basis})
        return Association.from_dict(payload)

    async def know(
        self,
        ref: str,
        *,
        as_of: str | None = None,
        entity_type: str | None = None,
        as_of_basis: str = "ingest",
    ) -> Knowledge:
        """EVERY belief about one subject — exhaustive, unlike :meth:`recall`.

        The counterpart to :meth:`recall`: recall retrieves by cue and may miss,
        ``know`` is direct access to everything held about a subject.

        ``recall`` ranks by embedding distance and returns ``top_k``, so a fact
        can be absent from the answer without the caller being able to tell.
        When the question is "what do we know about X", use this.

        ``ref`` is an entity id (``product_msm_0808``) or a surface name
        (``MSM-0808``, ``MSM 0808``), resolved the way ingestion resolved it.
        ``as_of`` (ISO-8601) gives the beliefs as they stood then.
        """
        params: dict[str, Any] = {}
        if as_of:
            params["as_of"] = as_of
        if entity_type:
            params["entity_type"] = entity_type
        if as_of_basis != "ingest":
            params["as_of_basis"] = as_of_basis
        payload = await self._request(
            "GET", f"/entity/{ref}/etches", params=params or None)
        return Knowledge.from_dict(payload)

    async def sleep(self) -> SleepResult:
        """Run one consolidation tick now (batch → extract → fold)."""
        return SleepResult.from_dict(await self._request("POST", "/sleep"))

    async def export(self) -> ExportResult:
        """Dump all etches to JSON files on the server; returns them too."""
        return ExportResult.from_dict(await self._request("POST", "/export"))

    async def history(self, etch_id: str) -> History:
        """Version timeline of one etch (immutable snapshots)."""
        return History.from_dict(
            await self._request("GET", f"/etch/{etch_id}/history"))

    async def stats(self) -> Stats:
        """Queue depths and store counts."""
        return Stats.from_dict(await self._request("GET", "/stats"))

    async def health(self) -> Health:
        """Liveness probe plus active server configuration."""
        return Health.from_dict(await self._request("GET", "/health"))
