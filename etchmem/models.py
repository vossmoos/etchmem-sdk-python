"""Typed response models for the etchmem REST API.

Plain dataclasses — no runtime deps beyond the stdlib. Each model mirrors
the corresponding Pydantic response schema in etchmem-server.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class RememberResult:
    """Response of POST /remember."""
    id: str
    stored: bool
    status: str          # "new" | "duplicate"
    message: str

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "RememberResult":
        return cls(id=d["id"], stored=d["stored"], status=d["status"],
                   message=d.get("message", ""))


@dataclass
class RecallResult:
    """One hit from POST /recall — an etch (consolidated belief) or a raw signal."""
    id: str
    content: str
    score: float
    origin: str                     # "etch" | "signal"
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

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "RecallResult":
        return cls(**{k: d.get(k) for k in (
            "id", "content", "score", "origin", "entity_name", "property",
            "value", "status", "confidence", "version", "scope", "source",
            "updated_at")} | {"created_at": d.get("created_at", 0.0)})


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

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "SleepResult":
        return cls(**{k: d.get(k, 0) for k in (
            "batched", "extracted_signals", "claims_written", "pairs_folded",
            "etches_formed", "etches_updated", "contested")})


@dataclass
class Etch:
    """One consolidated belief, as returned by POST /export."""
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

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Etch":
        return cls(
            id=d["id"], entity_name=d["entity_name"], property=d["property"],
            current_value=d["current_value"], status=d["status"],
            confidence=d["confidence"], narrative=d.get("narrative", ""),
            version=d["version"], created_at=d.get("created_at", 0.0),
            updated_at=d.get("updated_at", 0.0), scope=d.get("scope"),
            source=d.get("source"), claim_ids=d.get("claim_ids", []) or [],
            source_ids=d.get("source_ids", []) or [])


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


@dataclass
class EtchVersion:
    """One immutable snapshot from GET /etch/{id}/history."""
    version: int
    current_value: str
    status: str
    confidence: float
    narrative: str
    created_at: float
    triggered_by: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "EtchVersion":
        return cls(version=d["version"], current_value=d["current_value"],
                   status=d["status"], confidence=d["confidence"],
                   narrative=d.get("narrative", ""),
                   created_at=d.get("created_at", 0.0),
                   triggered_by=d.get("triggered_by", []) or [])


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

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Stats":
        return cls(**{k: d.get(k, 0) for k in (
            "signals_total", "signals_new", "signals_batched",
            "signals_extracted", "claims", "entities", "etches", "contested")}
            | {"scopes": d.get("scopes", []) or []})


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
