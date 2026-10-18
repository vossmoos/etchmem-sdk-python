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


# Server 0.0.9 shapes (label + detail, evidence, relations, filtered list).
EVIDENCE = {"signals": 2, "max_trust": 0.9, "sources": [
    {"source": "slack.reject", "trust": 0.9, "signals": 1},
    {"source": "qa.agent", "trust": 0.6, "signals": 1}]}
DETAILS = [{"value": "vector-db framing",
            "detail": "Never call etchmem a vector database."}]
ETCH_FULL = {
    "id": "etchmem::qa_rejection", "entity_name": "etchmem",
    "property": "qa_rejection", "current_value": "vector-db framing",
    "status": "settled", "confidence": 0.96, "narrative": "Editors reject it.",
    "version": 1, "scope": "content-qa", "source": "slack.reject",
    "value_entity_id": None, "details": DETAILS, "evidence": EVIDENCE,
    "claim_ids": ["c1"], "source_ids": ["s1", "s2"],
    "created_at": 1.0, "updated_at": 2.0}
KNOW_BODY = {"entity": {"id": "product_msm_0808", "name": "MSM-0808",
                        "type": "product", "aliases": ["MSM 0808"]},
             "etches": [ETCH_FULL | {"id": "e1", "status": "settled", "confidence": 0.9},
                        ETCH_FULL | {"id": "e2", "status": "contested", "confidence": 0.5},
                        ETCH_FULL | {"id": "e3", "status": "settled", "confidence": 0.4}],
             "count": 3, "as_of": None, "as_of_basis": "event", "contested": 1}
ASSOCIATE_BODY = {"query": "bathroom leaks", "seeds": [], "edges": [],
                  "nodes": [{"entity": {"id": "p1", "name": "DK-1120", "type": "part",
                                        "aliases": []},
                             "etches": [], "hops": 1, "score": 0.6,
                             "reached_via": "fix_procedure"}],
                  "as_of": None, "contested": 0}
RECALL_FULL_BODY = {"query": "draft", "as_of": None, "results": [
    {"id": "etchmem::qa_rejection", "content": "Editors reject it.", "score": 0.71,
     "origin": "etch", "entity_id": "etchmem", "entity_name": "etchmem",
     "property": "qa_rejection", "value": "vector-db framing", "status": "settled",
     "confidence": 0.96, "version": 1, "scope": "content-qa", "source": None,
     "details": DETAILS, "evidence": EVIDENCE, "created_at": 1.0, "updated_at": 2.0}]}
DOSSIER_BODY = {
    "etch": ETCH_FULL,
    "versions": [{"version": 1, "current_value": "vector-db framing",
                  "status": "settled", "confidence": 0.96, "narrative": "n",
                  "details": DETAILS, "evidence": EVIDENCE, "triggered_by": ["c1"],
                  "created_at": 2.0, "event_at": 1.5}],
    "claims": [{"id": "c1", "entity_name": "etchmem", "property": "qa_rejection",
                "value": "vector-db framing", "polarity": "asserted",
                "detail": "Never call etchmem a vector database.",
                "corroboration_count": 2, "confidence": 0.7,
                "sources": ["slack.reject", "qa.agent"],
                "evidence_signal_ids": ["s1", "s2"], "scope": "content-qa",
                "event_time": 1.5, "ingest_time": 2.0, "created_at": 2.0}],
    "signals": [{"id": "s1", "content": "Rejected: never call ...",
                 "source": "slack.reject", "scope": "content-qa",
                 "created_at": 2.0, "occurred_at": 1.5}],
    "signals_omitted": False}
SIGNAL_BODY = {
    "id": "sig-1", "content": "Slack — Andrey: As an idea, we add the links.",
    "source": "slack", "scope": "lift", "status": "extracted", "canonical_id": "sig-1",
    "context": "slack:C1:1.0", "context_parent": "slack:C1",
    "metadata": {"channel": "C1", "ts": "1.0", "subjects": [
        {"name": "followup-3", "entity_type": "feature", "existing": True,
         "quote": "the links", "reason": "the thread is about followup-3", "in_focus": True}],
        "associations": [{"name": "LIFT-22", "entity_type": "ticket",
                          "reason": "earlier followup work, done"}],
        "focus": ["followup-3 (feature)"],
        "meaning": "The links idea for followup-3 is agreed."},
    "created_at": 2.0, "occurred_at": 1.5,
    "claims": [{"id": "c9", "entity_name": "followup-3", "property": "idea",
                "value": "add links", "polarity": "asserted", "detail": "As an idea, we add the links.",
                "corroboration_count": 1, "confidence": 0.85, "sources": ["slack"],
                "evidence_signal_ids": ["sig-1"], "scope": "lift",
                "event_time": 1.5, "ingest_time": 2.0, "created_at": 2.0}]}
CONTEXT_BODY = {"id": "slack:C1:1.0",
                "focus": [{"entity_id": "ticket_lift_38", "name": "LIFT-38", "entity_type": "ticket",
                           "mentions": 1, "last_seen_at": 3.0},
                          {"entity_id": "feature_followup_3", "name": "followup-3",
                           "entity_type": "feature", "mentions": 2, "last_seen_at": 2.0}],
                "signals": [{"id": "sig-1", "content": "x", "source": "slack", "status": "extracted",
                             "context": "slack:C1:1.0", "occurred_at": 1.5}]}
SIGNAL_NEW_BODY = {"id": "sig-2", "content": "x", "source": "slack", "scope": "lift",
                   "status": "new", "canonical_id": None, "metadata": {"ts": "2.0"},
                   "created_at": 3.0, "occurred_at": 0.0, "claims": []}
SIGNAL_NONE_BODY = SIGNAL_NEW_BODY | {"id": "sig-3", "status": "extracted",
                                      "metadata": {"subjects": []}}
SLEEP_FULL_BODY = SLEEP_BODY | {
    "claims_dropped": 1, "claims_unsupported": 4, "subject_retries": 2, "relations_resolved": 3,
    "entities": {"entities_by_key": 5, "entities_by_fuzzy": 0}}
STATS_FULL_BODY = STATS_BODY | {"sources_without_trust": ["crm.note"]}


def etches_page(request: httpx.Request, total: int = 3) -> dict:
    """GET /etches: serve `total` etches, paged by limit/offset like the server."""
    limit = int(request.url.params.get("limit", 500))
    offset = int(request.url.params.get("offset", 0))
    ids = [f"e{i}" for i in range(total)][offset:offset + limit]
    rows = [ETCH_FULL | {"id": i, "entity_type": "product"} for i in ids]
    return {"etches": rows, "count": len(rows), "total": total,
            "limit": limit, "offset": offset}


def make_handler(captured: dict, full: bool = False):
    def handler(request: httpx.Request) -> httpx.Response:
        captured["request"] = request
        captured.setdefault("requests", []).append(request)
        routes = {
            ("POST", "/remember"): REMEMBER_BODY,
            ("POST", "/recall"): RECALL_FULL_BODY if full else RECALL_BODY,
            ("POST", "/sleep"): SLEEP_FULL_BODY if full else SLEEP_BODY,
            ("POST", "/export"): EXPORT_BODY,
            ("POST", "/associate"): ASSOCIATE_BODY,
            ("GET", "/entity/MSM-0808/etches"): KNOW_BODY,
            ("GET", "/entity/MSM 0808/etches"): KNOW_BODY,
            ("GET", "/etch/etch-1/history"): HISTORY_BODY,
            ("GET", "/etch/etchmem::qa_rejection/dossier"): DOSSIER_BODY,
            ("GET", "/signal/sig-1"): SIGNAL_BODY,
            ("GET", "/context/slack:C1:1.0"): CONTEXT_BODY,
            ("GET", "/signal/sig-2"): SIGNAL_NEW_BODY,
            ("GET", "/signal/sig-3"): SIGNAL_NONE_BODY,
            ("GET", "/stats"): STATS_FULL_BODY if full else STATS_BODY,
            ("GET", "/health"): HEALTH_BODY,
        }
        key = (request.method, request.url.path)
        if key == ("GET", "/etches"):
            return httpx.Response(200, json=etches_page(request))
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


# ── server 0.0.9 surface: know / associate / etches / dossier / new fields ──


@pytest.fixture()
def full_mem():
    captured: dict = {}
    client = httpx.Client(base_url=BASE,
                          transport=httpx.MockTransport(make_handler(captured, full=True)))
    m = EtchMem(BASE, client=client)
    m.captured = captured
    yield m
    m.close()


@pytest.fixture()
def full_amem():
    captured: dict = {}
    client = httpx.AsyncClient(
        base_url=BASE, transport=httpx.MockTransport(make_handler(captured, full=True)))
    m = AsyncEtchMem(BASE, client=client)
    m.captured = captured
    return m


def test_know_parses_and_filters_settled(full_mem):
    # 0.3.0 raised NameError here: Knowledge was never imported in the client.
    k = full_mem.know("MSM-0808", as_of="2026-09-10", as_of_basis="event")
    assert k.entity.name == "MSM-0808" and len(k) == 3
    assert k.contested == 1 and k.as_of_basis == "event"
    assert [e.id for e in k.settled(min_confidence=0.6)] == ["e1"]
    params = full_mem.captured["request"].url.params
    assert params["as_of"] == "2026-09-10" and params["as_of_basis"] == "event"


def test_know_encodes_ref_in_path(full_mem):
    full_mem.know("MSM 0808")
    assert full_mem.captured["request"].url.raw_path == b"/entity/MSM%200808/etches"


def test_associate(full_mem):
    # 0.3.0 raised NameError here: Association was never imported in the client.
    a = full_mem.associate("bathroom leaks", min_score=0.2)
    assert a.named("part")[0]["reached_via"] == "fix_procedure"
    sent = json.loads(full_mem.captured["request"].content)
    assert sent["min_score"] == 0.2 and sent["hops"] == 1


def test_recall_details_and_evidence(full_mem):
    hit = list(full_mem.recall("draft", scope="content-qa", include_signals=False))[0]
    assert hit.details[0].value == "vector-db framing"
    assert hit.details[0].detail.startswith("Never call")
    assert hit.evidence.max_trust == 0.9
    assert [s.source for s in hit.evidence.sources] == ["slack.reject", "qa.agent"]


def test_etches_filters_become_repeated_params(full_mem):
    page = full_mem.etches(scope="content-qa", property=["qa_rejection", "tone"],
                           entity_type="product", min_confidence=0.8, limit=2)
    params = full_mem.captured["request"].url.params
    assert params.get_list("property") == ["qa_rejection", "tone"]
    assert params.get_list("entity_type") == ["product"]
    assert params["scope"] == "content-qa" and params["min_confidence"] == "0.8"
    assert "status" not in params
    assert len(page) == 2 and page.total == 3 and page.has_more
    assert page.etches[0].entity_type == "product"
    assert page.etches[0].details[0].value == "vector-db framing"


def test_iter_etches_walks_every_page(full_mem):
    ids = [e.id for e in full_mem.iter_etches(page_size=2, scope="content-qa")]
    assert ids == ["e0", "e1", "e2"]
    offsets = [r.url.params["offset"] for r in full_mem.captured["requests"]]
    assert offsets == ["0", "2"]


def test_dossier(full_mem):
    d = full_mem.dossier("etchmem::qa_rejection")
    assert d.etch.evidence.signals == 2
    assert d.versions[0].event_at == 1.5 and d.versions[0].details
    assert d.claims[0].corroboration_count == 2 and d.claims[0].detail
    assert d.signals[0].occurred_at == 1.5 and d.signals_omitted is False


def test_signal_reports_status_subjects_and_claims(full_mem):
    r = full_mem.signal("sig-1")
    assert r.extracted and r.status == "extracted" and r.occurred_at == 1.5
    assert [(s.name, s.entity_type, s.existing) for s in r.subjects] == [("followup-3", "feature", True)]
    assert r.subjects[0].quote == "the links"
    assert [(c.entity_name, c.property, c.value) for c in r.claims] == [("followup-3", "idea", "add links")]
    assert r.metadata["channel"] == "C1"


def test_signal_context_focus_and_associations(full_mem):
    r = full_mem.signal("sig-1")
    assert (r.context, r.context_parent) == ("slack:C1:1.0", "slack:C1")
    assert r.focus == ["followup-3 (feature)"] and r.subjects[0].in_focus
    assert r.meaning == "The links idea for followup-3 is agreed."
    assert [(a.name, a.reason) for a in r.associations] == [("LIFT-22", "earlier followup work, done")]
    old = full_mem.signal("sig-2")                         # deposited without a context
    assert old.context is None and old.focus is None and old.associations == []
    assert old.meaning == ""


def test_context_record(full_mem):
    c = full_mem.context("slack:C1:1.0")
    assert [f.name for f in c.focus] == ["LIFT-38", "followup-3"] and c.focus[1].mentions == 2
    assert [x.id for x in c.signals] == ["sig-1"]


def test_remember_sends_the_context(mem):
    mem.remember("this ticket is done", source="slack", scope="lift",
                 context="slack:C1:1.0", context_parent="slack:C1")
    sent = json.loads(mem.captured["request"].content)
    assert (sent["context"], sent["context_parent"]) == ("slack:C1:1.0", "slack:C1")
    mem.remember("x", source="a", scope="s")
    sent = json.loads(mem.captured["request"].content)
    assert sent["context"] is None and sent["context_parent"] is None


def test_signal_not_yet_extracted_and_about_nothing(full_mem):
    pending = full_mem.signal("sig-2")
    assert not pending.extracted and pending.claims == [] and pending.subjects is None
    nothing = full_mem.signal("sig-3")
    assert nothing.extracted and nothing.subjects == []


def test_signal_unknown_id_raises_not_found(full_mem):
    with pytest.raises(NotFoundError):
        full_mem.signal("nope")


def test_sleep_and_stats_new_counters(full_mem):
    t = full_mem.sleep()
    assert (t.claims_dropped, t.subject_retries, t.relations_resolved) == (1, 2, 3)
    assert t.claims_unsupported == 4
    assert t.entities["entities_by_key"] == 5
    assert full_mem.stats().sources_without_trust == ["crm.note"]


def test_older_server_payloads_still_parse(mem):
    # A 0.0.4 server omits every new field; defaults must fill them.
    hit = list(mem.recall("acme"))[0]
    assert hit.details == [] and hit.evidence is None
    v = list(mem.history("etch-1"))[0]
    assert v.event_at == 0.0 and v.details == [] and v.evidence is None
    assert mem.stats().sources_without_trust == []
    assert mem.sleep().entities == {}


async def test_async_new_surface(full_amem):
    async with full_amem:
        assert (await full_amem.know("MSM-0808")).contested == 1
        assert (await full_amem.associate("leaks")).nodes
        assert (await full_amem.etches(property="qa_rejection")).total == 3
        ids = [e.id async for e in full_amem.iter_etches(page_size=2)]
        assert ids == ["e0", "e1", "e2"]
        assert (await full_amem.dossier("etchmem::qa_rejection")).claims
        assert (await full_amem.signal("sig-1")).subjects[0].name == "followup-3"
        assert (await full_amem.context("slack:C1:1.0")).focus[0].name == "LIFT-38"


def test_values_and_retracted_parse():
    from etchmem.models import Etch, EtchVersion, RecallResult
    vals = [{"value": "parquet export", "weight": 0.91, "active": True,
             "last_asserted_at": 2.0, "retracted_at": None},
            {"value": "csv export", "weight": 0.09, "active": False,
             "last_asserted_at": 1.0, "retracted_at": 3.0}]
    e = Etch.from_dict(ETCH_FULL | {"values": vals})
    assert [v.value for v in e.values] == ["parquet export", "csv export"]
    assert [v.value for v in e.retracted] == ["csv export"]
    assert e.retracted[0].retracted_at == 3.0
    hit = RecallResult.from_dict(RECALL_FULL_BODY["results"][0] | {"values": vals})
    assert hit.values[1].active is False
    v = EtchVersion.from_dict(DOSSIER_BODY["versions"][0] | {"values": vals})
    assert v.values[0].weight == 0.91
    assert Etch.from_dict(ETCH_FULL).values == []          # older server
