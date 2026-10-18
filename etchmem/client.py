"""Synchronous client for the etchmem-server REST API."""
from __future__ import annotations

import os
from collections.abc import Iterator, Sequence
from typing import Any
from urllib.parse import quote

import httpx

from etchmem.errors import ConnectionError, error_for_status
from etchmem.models import (
    Association, Dossier, Etch, EtchList, ExportResult, Health, History,
    Knowledge, RecallResponse, RememberResult, SleepResult, Stats, SignalRecord,
)

DEFAULT_BASE_URL = "http://localhost:8000"
DEFAULT_TIMEOUT = 30.0


def _etch_filters(scope: str | None, property: str | Sequence[str] | None,
                  entity_type: str | Sequence[str] | None, status: str | None,
                  min_confidence: float | None, limit: int,
                  offset: int) -> dict[str, Any]:
    """Query params for GET /etches; list filters become repeated params."""
    params: dict[str, Any] = {"limit": limit, "offset": offset}
    for key, value in (("scope", scope), ("status", status),
                       ("min_confidence", min_confidence)):
        if value is not None:
            params[key] = value
    for key, value in (("property", property), ("entity_type", entity_type)):
        if value:
            params[key] = [value] if isinstance(value, str) else list(value)
    return params


def _ref_path(ref: str) -> str:
    """Percent-encode an entity ref for the URL path ("MSM 0808", "R&D #4")."""
    return quote(ref, safe="")


class EtchMem:
    """Synchronous etchmem client.

    Usage::

        from etchmem import EtchMem

        mem = EtchMem("http://localhost:8000")
        mem.remember("Acme signed the Q3 renewal at $40k.",
                     source="agent-33", scope="sales")
        for hit in mem.recall("what did Acme sign?"):
            print(hit.content, hit.confidence)

    Can be used as a context manager to close the underlying HTTP
    connection pool deterministically::

        with EtchMem() as mem:
            mem.remember(...)

    Configuration falls back to environment variables:
    ``ETCHMEM_BASE_URL`` and ``ETCHMEM_API_KEY``.
    """

    def __init__(
        self,
        base_url: str | None = None,
        *,
        api_key: str | None = None,
        timeout: float = DEFAULT_TIMEOUT,
        client: httpx.Client | None = None,
    ) -> None:
        self.base_url = (base_url
                         or os.environ.get("ETCHMEM_BASE_URL")
                         or DEFAULT_BASE_URL).rstrip("/")
        self.api_key = api_key or os.environ.get("ETCHMEM_API_KEY")
        headers = {"Accept": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        self._client = client or httpx.Client(
            base_url=self.base_url, timeout=timeout)
        self._client.headers.update(headers)

    # ── lifecycle ──────────────────────────────────────────────────────

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "EtchMem":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()

    # ── internal ───────────────────────────────────────────────────────

    def _request(self, method: str, path: str,
                 json: dict[str, Any] | None = None,
                 params: dict[str, Any] | None = None) -> dict[str, Any]:
        try:
            resp = self._client.request(method, path, json=json, params=params)
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

    def remember(
        self,
        data: str,
        *,
        source: str,
        scope: str,
        extract_mode: str = "deferred",
        metadata: dict[str, Any] | None = None,
        occurred_at: str | float | None = None,
    ) -> RememberResult:
        """Deposit a raw text signal.

        ``extract_mode='immediate'`` marks the signal urgent (extracted on
        the next worker tick); ``'deferred'`` (default) batches it cheaply.
        Idempotent: re-depositing identical content returns ``stored=False``.

        ``occurred_at`` (ISO-8601 or epoch seconds) declares when the content
        actually happened; it defaults to ingest time. Always set it when
        loading historical records — otherwise every signal carries today's
        date and the server cannot order them against each other. The result
        echoes the parsed value so a bulk load can verify it was understood.
        """
        payload = self._request("POST", "/remember", json={
            "data": data, "source": source, "scope": scope,
            "extract_mode": extract_mode, "metadata": metadata or {},
            "occurred_at": occurred_at})
        return RememberResult.from_dict(payload)

    def recall(
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
        """Semantic recall over consolidated etches (plus fresh raw signals).

        Pass ``as_of`` (ISO-8601) for time-travel recall: results reflect
        what the system believed at that ingest time.
        """
        payload = self._request("POST", "/recall", json={
            "query": query, "scope": scope, "source": source, "top_k": top_k,
            "include_signals": include_signals, "as_of": as_of,
            "as_of_basis": as_of_basis})
        return RecallResponse.from_dict(payload)

    def associate(
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
        payload = self._request("POST", "/associate", json={
            "query": query, "scope": scope, "top_k": top_k, "hops": hops,
            "as_of": as_of, "min_score": min_score,
            "as_of_basis": as_of_basis})
        return Association.from_dict(payload)

    def know(
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
        payload = self._request(
            "GET", f"/entity/{_ref_path(ref)}/etches", params=params or None)
        return Knowledge.from_dict(payload)

    def etches(
        self,
        *,
        scope: str | None = None,
        property: str | Sequence[str] | None = None,
        entity_type: str | Sequence[str] | None = None,
        status: str | None = None,
        min_confidence: float | None = None,
        limit: int = 500,
        offset: int = 0,
    ) -> EtchList:
        """EVERY belief matching plain filters — exhaustive, not ranked.

        Use when you know the *kind* of belief rather than the subject or the
        words: "all qa_rejection rules in scope content-qa", "every contested
        lifecycle_status". ``property`` and ``entity_type`` take one value or a
        list. Returns one page (newest first); ``total`` counts every match, so
        page with ``offset`` or use :meth:`iter_etches`.
        """
        return EtchList.from_dict(self._request(
            "GET", "/etches", params=_etch_filters(
                scope, property, entity_type, status, min_confidence, limit, offset)))

    def iter_etches(self, *, page_size: int = 500, **filters: Any) -> Iterator[Etch]:
        """Every belief matching the filters of :meth:`etches`, across all pages."""
        offset = 0
        while True:
            page = self.etches(limit=page_size, offset=offset, **filters)
            yield from page.etches
            if not page.has_more or not page.etches:
                return
            offset += page.count

    def sleep(self) -> SleepResult:
        """Run one consolidation tick now (batch → extract → fold)."""
        return SleepResult.from_dict(self._request("POST", "/sleep"))

    def export(self) -> ExportResult:
        """Dump all etches to JSON files on the server; returns them too."""
        return ExportResult.from_dict(self._request("POST", "/export"))

    def history(self, etch_id: str) -> History:
        """Version timeline of one etch (immutable snapshots)."""
        return History.from_dict(
            self._request("GET", f"/etch/{etch_id}/history"))

    def dossier(self, etch_id: str) -> Dossier:
        """Full provenance of one belief: etch, versions, claims, raw signals.

        The answer to "why does the agent believe that?". Raw signals are
        withheld (``signals_omitted=True``) when the server anonymizes claims.
        """
        return Dossier.from_dict(
            self._request("GET", f"/etch/{etch_id}/dossier"))

    def signal(self, signal_id: str) -> SignalRecord:
        """What one deposited signal became: its status, the subjects it was found
        to be about, and every claim extracted from it (server 0.2.0+).

        Use the id ``remember`` returned. etchmem only records; whether that is
        enough for your task is yours to decide — for example by asking your
        user and depositing the answer as a new signal.
        """
        return SignalRecord.from_dict(
            self._request("GET", f"/signal/{signal_id}"))

    def stats(self) -> Stats:
        """Queue depths and store counts."""
        return Stats.from_dict(self._request("GET", "/stats"))

    def health(self) -> Health:
        """Liveness probe plus active server configuration."""
        return Health.from_dict(self._request("GET", "/health"))
