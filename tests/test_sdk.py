"""SDK unit tests — httpx MockTransport, no live server needed."""
from __future__ import annotations

import json

import httpx
import pytest

from etchmem import (
    AsyncEtchMem, AuthenticationError, ConnectionError, EtchMem,
    NotFoundError, ServerError,
)

BASE = "http://testserver"

REMEMBER_BODY = {"id": "sig-1", "stored": True, "status": "new", "message": "Accepted."}
RECALL_BODY = {
    "query": "acme", "as_of": None,
    "results": [{
        "id": "etch-1", "content": "Acme renewal is $40k.", "score": 0.91,
        "origin": "etch", "entity_name": "Acme", "property": "renewal_value",
        "value": "$40k", "status": "settled", "confidence": 0.8, "version": 2,
        "scope": "sales", "source": None, "created_at": 1.0, "updated_at": 2.0,
    }],
}
SLEEP_BODY = {"batched": 3, "extracted_signals": 2, "claims_written": 5,
              "pairs_folded": 4, "etches_formed": 1, "etches_updated": 1,
              "contested": 0}
EXPORT_BODY = {"export_dir": "/data/export", "count": 1, "etches": [{
    "id": "etch-1", "entity_name": "Acme", "property": "renewal_value",
    "current_value": "$40k", "status": "settled", "confidence": 0.8,
    "narrative": "Two sources agree.", "version": 2, "scope": "sales",
    "source": None, "claim_ids": ["c1"], "source_ids": ["s1"],
    "created_at": 1.0, "updated_at": 2.0}]}
HISTORY_BODY = {"etch_id": "etch-1", "versions": [
    {"version": 1, "current_value": "$35k", "status": "settled",
     "confidence": 0.5, "narrative": "First claim.", "triggered_by": ["c1"],
     "created_at": 1.0},
    {"version": 2, "current_value": "$40k", "status": "settled",
     "confidence": 0.8, "narrative": "Corroborated.", "triggered_by": ["c2"],
     "created_at": 2.0}]}
STATS_BODY = {"signals_total": 10, "signals_new": 1, "signals_batched": 2,
              "signals_extracted": 7, "claims": 12, "entities": 3,
              "etches": 5, "contested": 1, "scopes": ["sales"]}
HEALTH_BODY = {"status": "ok", "version": "0.1.0",
               "embedding_provider": "openai", "embedding_dim": 1536,
               "claim_model": "mini", "etch_model": "top",
               "worker_enabled": True, "claims_anonymization": False}


def make_handler(captured: dict):
    def handler(request: httpx.Request) -> httpx.Response:
        captured["request"] = request
        routes = {
            ("POST", "/remember"): REMEMBER_BODY,
            ("POST", "/recall"): RECALL_BODY,
            ("POST", "/sleep"): SLEEP_BODY,
            ("POST", "/export"): EXPORT_BODY,
            ("GET", "/etch/etch-1/history"): HISTORY_BODY,
            ("GET", "/stats"): STATS_BODY,
            ("GET", "/health"): HEALTH_BODY,
        }
        key = (request.method, request.url.path)
        if key in routes:
            return httpx.Response(200, json=routes[key])
        return httpx.Response(404, json={"detail": "not found"})
    return handler


@pytest.fixture()
def mem():
    captured: dict = {}
    transport = httpx.MockTransport(make_handler(captured))
    client = httpx.Client(base_url=BASE, transport=transport)
    m = EtchMem(BASE, client=client)
    m.captured = captured
    yield m
    m.close()


@pytest.fixture()
def amem():
    captured: dict = {}
    transport = httpx.MockTransport(make_handler(captured))
    client = httpx.AsyncClient(base_url=BASE, transport=transport)
    m = AsyncEtchMem(BASE, client=client)
    m.captured = captured
    return m


# ── sync ───────────────────────────────────────────────────────────────


def test_remember(mem):
    r = mem.remember("Acme signed.", source="agent-33", scope="sales")
    assert r.stored is True and r.id == "sig-1" and r.status == "new"
    sent = json.loads(mem.captured["request"].content)
    assert sent["extract_mode"] == "deferred"
    assert sent["metadata"] == {}


def test_remember_immediate(mem):
    mem.remember("x", source="a", scope="s", extract_mode="immediate",
                 metadata={"k": "v"})
    sent = json.loads(mem.captured["request"].content)
    assert sent["extract_mode"] == "immediate" and sent["metadata"] == {"k": "v"}


def test_recall(mem):
    resp = mem.recall("acme", top_k=3, as_of="2026-06-01T00:00:00Z")
    assert len(resp) == 1
    hit = list(resp)[0]
    assert hit.origin == "etch" and hit.confidence == 0.8
    sent = json.loads(mem.captured["request"].content)
    assert sent["top_k"] == 3 and sent["as_of"] == "2026-06-01T00:00:00Z"


def test_sleep(mem):
    t = mem.sleep()
    assert t.etches_formed == 1 and t.contested == 0


def test_export(mem):
    e = mem.export()
    assert e.count == 1 and e.etches[0].entity_name == "Acme"
    assert e.etches[0].claim_ids == ["c1"]


def test_history(mem):
    h = mem.history("etch-1")
    assert len(h) == 2
    assert [v.version for v in h] == [1, 2]


def test_stats_and_health(mem):
    s = mem.stats()
    assert s.etches == 5 and s.scopes == ["sales"]
    hl = mem.health()
    assert hl.status == "ok" and hl.embedding_dim == 1536


def test_not_found(mem):
    with pytest.raises(NotFoundError) as ei:
        mem.history("missing")
    assert ei.value.status_code == 404


def test_server_error():
    transport = httpx.MockTransport(
        lambda req: httpx.Response(500, json={"detail": "boom"}))
    m = EtchMem(BASE, client=httpx.Client(base_url=BASE, transport=transport))
    with pytest.raises(ServerError):
        m.sleep()


def test_auth_error():
    transport = httpx.MockTransport(
        lambda req: httpx.Response(401, json={"detail": "no key"}))
    m = EtchMem(BASE, client=httpx.Client(base_url=BASE, transport=transport))
    with pytest.raises(AuthenticationError):
        m.stats()


def test_connection_error():
    def raise_err(req):
        raise httpx.ConnectError("refused")
    m = EtchMem(BASE, client=httpx.Client(
        base_url=BASE, transport=httpx.MockTransport(raise_err)))
    with pytest.raises(ConnectionError):
        m.health()


def test_api_key_header():
    captured: dict = {}
    client = httpx.Client(
        base_url=BASE, transport=httpx.MockTransport(make_handler(captured)))
    m = EtchMem(BASE, api_key="secret-123", client=client)
    m.health()
    assert captured["request"].headers["Authorization"] == "Bearer secret-123"
    m.close()


# ── async ──────────────────────────────────────────────────────────────


async def test_async_remember(amem):
    async with amem:
        r = await amem.remember("x", source="a", scope="s")
        assert r.id == "sig-1"


async def test_async_recall(amem):
    async with amem:
        resp = await amem.recall("acme")
        assert list(resp)[0].entity_name == "Acme"


async def test_async_history_stats_health(amem):
    async with amem:
        assert len(await amem.history("etch-1")) == 2
        assert (await amem.stats()).claims == 12
        assert (await amem.health()).worker_enabled is True
