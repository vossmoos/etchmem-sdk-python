"""
etchmem — Python SDK for the etchmem-server REST API.

The Knowledge Consolidation Engine for AI agents: raw signals in,
consolidated, versioned beliefs (etches) out.

Public surface::

    from etchmem import EtchMem, AsyncEtchMem

    mem = EtchMem("http://localhost:8000")
    mem.remember("Acme signed the Q3 renewal at $40k.",
                 source="agent-33", scope="sales")
    hits = mem.recall("what did Acme sign?")

Note: the server also exposes an MCP interface at ``/mcp``. MCP clients
connect to it directly with the MCP protocol — no SDK needed there. This
package is for REST integrations.
"""
from etchmem.async_client import AsyncEtchMem
from etchmem.client import EtchMem
from etchmem.errors import (
    APIError, AuthenticationError, ConnectionError, EtchMemError,
    NotFoundError, ServerError,
)
from etchmem.models import (
    Association, Claim, DetailItem, Dossier, EntityInfo, Etch, EtchList,
    EtchVersion, Evidence, ExportResult, Health, History, Knowledge,
    RecallResponse, RecallResult, RememberResult, Signal, SleepResult,
    SourceEvidence, Stats, ValueWeight,
)

__all__ = [
    "EtchMem",
    "AsyncEtchMem",
    # models
    "RememberResult",
    "RecallResponse",
    "RecallResult",
    "Association",
    "EntityInfo",
    "Knowledge",
    "SleepResult",
    "ExportResult",
    "Etch",
    "EtchList",
    "EtchVersion",
    "History",
    "Dossier",
    "Claim",
    "Signal",
    "DetailItem",
    "Evidence",
    "SourceEvidence",
    "ValueWeight",
    "Stats",
    "Health",
    # errors
    "EtchMemError",
    "APIError",
    "ConnectionError",
    "AuthenticationError",
    "NotFoundError",
    "ServerError",
]

__version__ = "0.4.0"
