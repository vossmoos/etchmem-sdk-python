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
                       json: dict[str, Any] | None = None) -> dict[str, Any]:
        try:
            resp = await self._client.request(method, path, json=json)
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
    ) -> RememberResult:
        """Deposit a raw text signal (see :meth:`etchmem.EtchMem.remember`)."""
        payload = await self._request("POST", "/remember", json={
            "data": data, "source": source, "scope": scope,
            "extract_mode": extract_mode, "metadata": metadata or {}})
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
    ) -> RecallResponse:
        """Semantic recall over etches; ``as_of`` enables time-travel."""
        payload = await self._request("POST", "/recall", json={
            "query": query, "scope": scope, "source": source, "top_k": top_k,
            "include_signals": include_signals, "as_of": as_of})
        return RecallResponse.from_dict(payload)

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
