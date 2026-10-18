"""Typed response models for the etchmem REST API.

Plain dataclasses — no runtime deps beyond the stdlib. Each model mirrors
the corresponding Pydantic response schema in etchmem-server.

New fields are always appended with defaults, so responses from an older
server (which simply omit them) still parse.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


# ── shared building blocks ─────────────────────────────────────────────────


@dataclass
class DetailItem:
    """One labelled fact: ``value`` is the short label, ``detail`` the author's
    full wording. Only properties declared ``detail: true`` carry these."""
    value: str
    detail: str

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "DetailItem":
        return cls(value=d.get("value", ""), detail=d.get("detail", "") or "")


def _details(raw: Any) -> list[DetailItem]:
    return [DetailItem.from_dict(x) for x in (raw or [])]


@dataclass
class ValueWeight:
    """One value ever asserted for a belief, heaviest first.

    A retracted value is not deleted: ``active`` is False and its ``weight``
    is much lower, so the memory knows it is no longer valid and that it was.
    """
    value: str
    weight: float = 0.0             # share of the belief's total weight, 0..1
    active: bool = True
    last_asserted_at: float | None = None
    retracted_at: float | None = None

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "ValueWeight":
        return cls(value=d.get("value", ""), weight=d.get("weight", 0.0) or 0.0,
                   active=bool(d.get("active", True)),
                   last_asserted_at=d.get("last_asserted_at"),
                   retracted_at=d.get("retracted_at"))


def _values(raw: Any) -> list[ValueWeight]:
    return [ValueWeight.from_dict(x) for x in (raw or [])]


@dataclass
class SourceEvidence:
    """One source behind a belief, with the trust declared when it was folded."""
    source: str
    trust: float
    signals: int

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "SourceEvidence":
        return cls(source=d["source"], trust=d.get("trust", 0.0),
                   signals=d.get("signals", 0))


@dataclass
class Evidence:
    """What a confidence rests on, so the number can be explained or re-judged
    ("only use beliefs backed by a source above 0.8")."""
    signals: int = 0
    sources: list[SourceEvidence] = field(default_factory=list)
    max_trust: float = 0.0

    @classmethod
    def from_dict(cls, d: dict[str, Any] | None) -> "Evidence | None":
        if not d:
            return None
        return cls(signals=d.get("signals", 0),
                   sources=[SourceEvidence.from_dict(s) for s in d.get("sources") or []],
                   max_trust=d.get("max_trust", 0.0))


# ── remember ───────────────────────────────────────────────────────────────


@dataclass
class RememberResult:
    """Response of POST /remember."""
    id: str
    stored: bool
    status: str          # "new" | "duplicate"
    message: str
    occurred_at: float = 0.0        # event time as stored, epoch seconds
    occurred_at_declared: bool = False   # False = ingest time was used

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "RememberResult":
        return cls(id=d["id"], stored=d["stored"], status=d["status"],
                   message=d.get("message", ""),
                   occurred_at=d.get("occurred_at", 0.0) or 0.0,
                   occurred_at_declared=bool(d.get("occurred_at_declared", False)))


# ── etches ─────────────────────────────────────────────────────────────────


@dataclass
class Etch:
    """One consolidated belief (export, know, etches, dossier)."""
    id: str
    entity_name: str
    property: str
    current_value: str
    status: str
    confidence: float
    narrative: str
    version: int
    created_at: float
    updated_at: float
    scope: str | None = None
    source: str | None = None
    claim_ids: list[str] = field(default_factory=list)
    source_ids: list[str] = field(default_factory=list)
    value_entity_id: str | None = None      # set when the property is a relation
    details: list[DetailItem] = field(default_factory=list)
    evidence: Evidence | None = None
    entity_type: str | None = None          # filled by GET /etches only
    values: list[ValueWeight] = field(default_factory=list)

    @property
    def retracted(self) -> list[ValueWeight]:
        """Values that were asserted once and later withdrawn."""
        return [v for v in self.values if not v.active]

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Etch":
        return cls(
            id=d["id"], entity_name=d["entity_name"], property=d["property"],
            current_value=d["current_value"], status=d["status"],
            confidence=d["confidence"], narrative=d.get("narrative", ""),
            version=d["version"], created_at=d.get("created_at", 0.0),
            updated_at=d.get("updated_at", 0.0), scope=d.get("scope"),
            source=d.get("source"), claim_ids=d.get("claim_ids", []) or [],
            source_ids=d.get("source_ids", []) or [],
            value_entity_id=d.get("value_entity_id"),
            details=_details(d.get("details")),
            evidence=Evidence.from_dict(d.get("evidence")),
            entity_type=d.get("entity_type"),
            values=_values(d.get("values")))


@dataclass
class EtchList:
    """Response of GET /etches — every belief matching the filters, one page.

    Exhaustive within the filters, not similarity-ranked. ``total`` counts all
    matches; page on with ``offset`` until :attr:`has_more` is False, or use
    ``iter_etches()`` on the client.
    """
    etches: list[Etch]
    count: int = 0
    total: int = 0
    limit: int = 0
    offset: int = 0

    def __iter__(self):
        return iter(self.etches)

    def __len__(self) -> int:
        return len(self.etches)

    @property
    def has_more(self) -> bool:
        return self.offset + self.count < self.total

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "EtchList":
        etches = [Etch.from_dict(e) for e in d.get("etches") or []]
        return cls(etches=etches, count=d.get("count", len(etches)),
                   total=d.get("total", len(etches)), limit=d.get("limit", 0),
                   offset=d.get("offset", 0))


# ── know / associate ───────────────────────────────────────────────────────


@dataclass
class EntityInfo:
    """The canonical subject a Knowledge answer is about."""
    id: str
    name: str
    type: str
    aliases: list[str]
    scope: str | None = None

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "EntityInfo":
        return cls(id=d["id"], name=d["name"], type=d["type"],
                   aliases=list(d.get("aliases") or []), scope=d.get("scope"))


@dataclass
class Knowledge:
    """Every belief about one subject — exhaustive, not similarity-ranked."""
    entity: EntityInfo
    etches: list[Etch]
    count: int = 0
    as_of: str | None = None
    contested: int = 0
    as_of_basis: str = "ingest"

    def __iter__(self):
        return iter(self.etches)

    def __len__(self) -> int:
        return len(self.etches)

    def settled(self, min_confidence: float = 0.0) -> list[Etch]:
        """Only beliefs safe to state as fact.

        A contested belief is one the engine could not settle; surfacing it as
        an answer is the failure this whole design exists to prevent. Use the
        contested ones to raise a question instead.
        """
        return [e for e in self.etches
                if e.status == "settled" and e.confidence >= min_confidence]

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Knowledge":
        return cls(entity=EntityInfo.from_dict(d["entity"]),
                   etches=[Etch.from_dict(e) for e in d.get("etches") or []],
                   count=d.get("count", 0), as_of=d.get("as_of"),
                   contested=d.get("contested", 0),
                   as_of_basis=d.get("as_of_basis", "ingest"))


@dataclass
class Association:
    """What the memory holds for a phrase: beliefs, subjects, connected nodes.

    ``seeds``, ``nodes`` and ``edges`` are kept as the server's plain dicts.
    """
    query: str
    seeds: list[Any]
    nodes: list[Any]
    edges: list[Any]
    contested: int = 0
    as_of: str | None = None

    def named(self, *types: str) -> list[Any]:
        """Nodes of these entity types, closest first."""
        return [n for n in self.nodes if not types or n["entity"]["type"] in types]

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Association":
        return cls(query=d["query"], seeds=d.get("seeds") or [],
                   nodes=d.get("nodes") or [], edges=d.get("edges") or [],
                   contested=d.get("contested", 0), as_of=d.get("as_of"))


# ── recall ─────────────────────────────────────────────────────────────────


@dataclass
class RecallResult:
    """One hit from POST /recall — an etch (consolidated belief) or a raw signal."""
    id: str
    content: str
    score: float
    origin: str                     # "etch" | "signal"
    entity_id: str | None = None    # subject slug — pass straight to know()
    entity_name: str | None = None
    property: str | None = None
    value: str | None = None
    status: str | None = None       # "settled" | "contested" (etches only)
    confidence: float | None = None
    version: int | None = None
    scope: str | None = None
    source: str | None = None
    created_at: float = 0.0
    updated_at: float | None = None
    details: list[DetailItem] = field(default_factory=list)
    evidence: Evidence | None = None
    values: list[ValueWeight] = field(default_factory=list)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "RecallResult":
        return cls(**{k: d.get(k) for k in (
            "id", "content", "score", "origin", "entity_id", "entity_name", "property",
            "value", "status", "confidence", "version", "scope", "source",
            "updated_at")} | {
            "created_at": d.get("created_at", 0.0),
            "details": _details(d.get("details")),
            "evidence": Evidence.from_dict(d.get("evidence")),
            "values": _values(d.get("values"))})


@dataclass
class RecallResponse:
    """Response of POST /recall."""
    query: str
    results: list[RecallResult]
    as_of: str | None = None

    def __iter__(self):
        return iter(self.results)

    def __len__(self) -> int:
        return len(self.results)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "RecallResponse":
        return cls(query=d["query"], as_of=d.get("as_of"),
                   results=[RecallResult.from_dict(r) for r in d.get("results", [])])


# ── sleep / export ─────────────────────────────────────────────────────────


@dataclass
class SleepResult:
    """Response of POST /sleep — counters for one worker tick."""
    batched: int
    extracted_signals: int
    claims_written: int
    pairs_folded: int
    etches_formed: int
    etches_updated: int
    contested: int
    claims_dropped: int = 0
    claims_unsupported: int = 0     # claims the verify step found the signal not to state
    subject_retries: int = 0        # rising = extractor prompt problem
    relations_resolved: int = 0
    entities: dict[str, int] = field(default_factory=dict)  # by_key / by_fuzzy / ...

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "SleepResult":
        return cls(**{k: d.get(k, 0) for k in (
            "batched", "extracted_signals", "claims_written", "pairs_folded",
            "etches_formed", "etches_updated", "contested", "claims_dropped",
            "claims_unsupported", "subject_retries", "relations_resolved")}
            | {"entities": dict(d.get("entities") or {})})


@dataclass
class ExportResult:
    """Response of POST /export."""
    export_dir: str
    count: int
    etches: list[Etch]

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "ExportResult":
        return cls(export_dir=d["export_dir"], count=d.get("count", 0),
                   etches=[Etch.from_dict(e) for e in d.get("etches", [])])


# ── history / dossier ──────────────────────────────────────────────────────


@dataclass
class EtchVersion:
    """One immutable snapshot from GET /etch/{id}/history.

    ``created_at`` is when we learned it; ``event_at`` when the fact behind it
    became true.
    """
    version: int
    current_value: str
    status: str
    confidence: float
    narrative: str
    created_at: float
    triggered_by: list[str] = field(default_factory=list)
    event_at: float = 0.0
    details: list[DetailItem] = field(default_factory=list)
    evidence: Evidence | None = None
    values: list[ValueWeight] = field(default_factory=list)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "EtchVersion":
        return cls(version=d["version"], current_value=d["current_value"],
                   status=d["status"], confidence=d["confidence"],
                   narrative=d.get("narrative", ""),
                   created_at=d.get("created_at", 0.0),
                   triggered_by=d.get("triggered_by", []) or [],
                   event_at=d.get("event_at", 0.0) or 0.0,
                   details=_details(d.get("details")),
                   evidence=Evidence.from_dict(d.get("evidence")),
                   values=_values(d.get("values")))


@dataclass
class History:
    """Response of GET /etch/{id}/history."""
    etch_id: str
    versions: list[EtchVersion]

    def __iter__(self):
        return iter(self.versions)

    def __len__(self) -> int:
        return len(self.versions)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "History":
        return cls(etch_id=d["etch_id"],
                   versions=[EtchVersion.from_dict(v) for v in d.get("versions", [])])


@dataclass
class Claim:
    """One typed assertion behind a belief (dossier)."""
    id: str
    entity_name: str
    property: str
    value: str
    polarity: str
    corroboration_count: int
    confidence: float
    detail: str | None = None
    sources: list[str] = field(default_factory=list)
    evidence_signal_ids: list[str] = field(default_factory=list)
    scope: str | None = None
    event_time: float = 0.0
    ingest_time: float = 0.0
    created_at: float = 0.0

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Claim":
        return cls(id=d["id"], entity_name=d["entity_name"], property=d["property"],
                   value=d["value"], polarity=d.get("polarity", "asserted"),
                   corroboration_count=d.get("corroboration_count", 1),
                   confidence=d.get("confidence", 0.0), detail=d.get("detail"),
                   sources=d.get("sources") or [],
                   evidence_signal_ids=d.get("evidence_signal_ids") or [],
                   scope=d.get("scope"), event_time=d.get("event_time", 0.0) or 0.0,
                   ingest_time=d.get("ingest_time", 0.0) or 0.0,
                   created_at=d.get("created_at", 0.0) or 0.0)


@dataclass
class Signal:
    """One raw deposit behind a belief (dossier)."""
    id: str
    content: str
    source: str
    scope: str
    created_at: float = 0.0
    occurred_at: float = 0.0

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Signal":
        return cls(id=d["id"], content=d.get("content", ""), source=d.get("source", ""),
                   scope=d.get("scope", ""), created_at=d.get("created_at", 0.0) or 0.0,
                   occurred_at=d.get("occurred_at", 0.0) or 0.0)


@dataclass
class Dossier:
    """Response of GET /etch/{id}/dossier — full provenance of one belief:
    the etch, its versions, the claims that formed it and the raw signals."""
    etch: Etch
    versions: list[EtchVersion]
    claims: list[Claim]
    signals: list[Signal] = field(default_factory=list)
    signals_omitted: bool = False   # True when claims anonymization hides raw text

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Dossier":
        return cls(etch=Etch.from_dict(d["etch"]),
                   versions=[EtchVersion.from_dict(v) for v in d.get("versions") or []],
                   claims=[Claim.from_dict(c) for c in d.get("claims") or []],
                   signals=[Signal.from_dict(s) for s in d.get("signals") or []],
                   signals_omitted=bool(d.get("signals_omitted", False)))


@dataclass
class ResolvedSubject:
    """What a signal was found to be about (server 0.2.0+): the subject, whether
    it already existed, the signal's own words that refer to it, and why."""
    name: str
    entity_type: str
    existing: bool
    quote: str = ""
    reason: str = ""
    in_focus: bool = False          # the conversation was already about it (0.3.0+)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "ResolvedSubject":
        return cls(name=d.get("name", ""), entity_type=d.get("entity_type", ""),
                   existing=bool(d.get("existing", False)), quote=d.get("quote", "") or "",
                   reason=d.get("reason", "") or "", in_focus=bool(d.get("in_focus", False)))


@dataclass
class AssociatedSubject:
    """Related knowledge a signal brought to mind — an earlier iteration, a ticket
    that already covers it — recorded with the reason. Never a claim (0.3.0+)."""
    name: str
    entity_type: str
    reason: str = ""

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "AssociatedSubject":
        return cls(name=d.get("name", ""), entity_type=d.get("entity_type", ""),
                   reason=d.get("reason", "") or "")


@dataclass
class SignalRecord:
    """Response of GET /signal/{id} — what one deposited signal became.

    ``status`` is ``new``, ``batched`` or ``extracted``; until it is
    ``extracted`` there are no claims yet. ``subjects`` is ``None`` while the
    signal is unresolved (or on a server without the resolve step) and ``[]``
    when it was found to be about no identifiable subject. ``content`` is
    ``None`` when the server anonymizes claims.
    """
    id: str
    source: str
    scope: str
    status: str
    content: str | None = None
    canonical_id: str | None = None
    context: str | None = None             # the conversation it was said in (0.3.0+)
    context_parent: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: float = 0.0
    occurred_at: float = 0.0
    claims: list[Claim] = field(default_factory=list)

    @property
    def extracted(self) -> bool:
        return self.status == "extracted"

    @property
    def subjects(self) -> list[ResolvedSubject] | None:
        raw = self.metadata.get("subjects")
        return None if raw is None else [ResolvedSubject.from_dict(x) for x in raw]

    @property
    def associations(self) -> list[AssociatedSubject]:
        """Related knowledge it brought to mind; recorded, never claims."""
        return [AssociatedSubject.from_dict(x) for x in self.metadata.get("associations") or []]

    @property
    def meaning(self) -> str:
        """For a reply that refers back ("let us implement that"): what it says with
        those references spelled out. Empty when the signal stands on its own (0.3.1+)."""
        return str(self.metadata.get("meaning") or "")

    @property
    def focus(self) -> list[str] | None:
        """What its conversation was about when it was said ("name (type)"),
        or None for a signal deposited without a context."""
        return self.metadata.get("focus")

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "SignalRecord":
        return cls(id=d["id"], source=d.get("source", ""), scope=d.get("scope", ""),
                   status=d.get("status", ""), content=d.get("content"),
                   canonical_id=d.get("canonical_id"), context=d.get("context"),
                   context_parent=d.get("context_parent"),
                   metadata=dict(d.get("metadata") or {}),
                   created_at=d.get("created_at", 0.0) or 0.0,
                   occurred_at=d.get("occurred_at", 0.0) or 0.0,
                   claims=[Claim.from_dict(c) for c in d.get("claims") or []])


@dataclass
class ContextSubject:
    entity_id: str
    name: str
    entity_type: str
    mentions: int = 0
    last_seen_at: float = 0.0

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "ContextSubject":
        return cls(entity_id=d["entity_id"], name=d.get("name", ""),
                   entity_type=d.get("entity_type", ""), mentions=d.get("mentions", 0) or 0,
                   last_seen_at=d.get("last_seen_at", 0.0) or 0.0)


@dataclass
class ContextSignal:
    id: str
    source: str
    status: str
    content: str | None = None
    context: str | None = None
    occurred_at: float = 0.0

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "ContextSignal":
        return cls(id=d["id"], source=d.get("source", ""), status=d.get("status", ""),
                   content=d.get("content"), context=d.get("context"),
                   occurred_at=d.get("occurred_at", 0.0) or 0.0)


@dataclass
class ContextRecord:
    """Response of GET /context/{id} — one conversation: what it has been about
    (most recent first) and its signals in the order they were said."""
    id: str
    focus: list[ContextSubject] = field(default_factory=list)
    signals: list[ContextSignal] = field(default_factory=list)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "ContextRecord":
        return cls(id=d["id"], focus=[ContextSubject.from_dict(x) for x in d.get("focus") or []],
                   signals=[ContextSignal.from_dict(x) for x in d.get("signals") or []])


# ── stats / health ─────────────────────────────────────────────────────────


@dataclass
class Stats:
    """Response of GET /stats — queue depths and store counts."""
    signals_total: int
    signals_new: int
    signals_batched: int
    signals_extracted: int
    claims: int
    entities: int
    etches: int
    contested: int
    scopes: list[str] = field(default_factory=list)
    sources_without_trust: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Stats":
        return cls(**{k: d.get(k, 0) for k in (
            "signals_total", "signals_new", "signals_batched",
            "signals_extracted", "claims", "entities", "etches", "contested")}
            | {"scopes": d.get("scopes", []) or [],
               "sources_without_trust": d.get("sources_without_trust", []) or []})


@dataclass
class Health:
    """Response of GET /health — liveness plus active server config."""
    status: str
    version: str
    embedding_provider: str
    embedding_dim: int
    claim_model: str
    etch_model: str
    worker_enabled: bool
    claims_anonymization: bool = False

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Health":
        return cls(status=d["status"], version=d["version"],
                   embedding_provider=d.get("embedding_provider", ""),
                   embedding_dim=d.get("embedding_dim", 0),
                   claim_model=d.get("claim_model", ""),
                   etch_model=d.get("etch_model", ""),
                   worker_enabled=d.get("worker_enabled", False),
                   claims_anonymization=d.get("claims_anonymization", False))
