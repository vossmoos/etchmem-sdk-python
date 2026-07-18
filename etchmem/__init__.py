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
    Etch, EtchVersion, ExportResult, Health, History, RecallResponse,
    RecallResult, RememberResult, SleepResult, Stats,
)

__all__ = [
    "EtchMem",
    "AsyncEtchMem",
    # models
    "RememberResult",
    "RecallResponse",
    "RecallResult",
    "SleepResult",
    "ExportResult",
    "Etch",
    "EtchVersion",
    "History",
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

__version__ = "0.2.0"
