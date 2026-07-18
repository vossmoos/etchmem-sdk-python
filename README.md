# etchmem

**Python SDK for [etchmem-server](https://github.com/vossmoos/etchmem-sdk-python) — the Knowledge Consolidation Engine for AI agents.**

Your agents' daily activity is full of hard-won facts — deals signed, decisions made, preferences learned. etchmem-server turns that stream of raw signals into a clean, typed, versioned knowledge base: one consolidated belief per fact, with confidence, provenance, conflict status, and full version history — queryable at any point in time.

This package is the REST client. One dependency (`httpx`), sync and async, fully typed responses.

```bash
pip install etchmem
```

> **Note on MCP:** etchmem-server also exposes an MCP interface at `/mcp` with the same operations as tools. MCP clients (Claude, agent frameworks, IDEs) connect to it directly over the MCP protocol — no SDK needed. This package is for REST integrations only.

---

## Quickstart

Run the server (see the etchmem-server repo — `docker compose up`), then:

```python
from etchmem import EtchMem

mem = EtchMem("http://localhost:8000")   # default; also reads ETCHMEM_BASE_URL

# Deposit a raw signal — no pre-structuring needed
mem.remember(
    "Acme signed the Q3 renewal at $40k. Maria approved the discount.",
    source="agent-33",
    scope="sales",
)

# Semantic recall over consolidated beliefs
for hit in mem.recall("what did Acme sign?", top_k=5):
    print(f"[{hit.origin}] {hit.content}  (confidence={hit.confidence})")
```

### Async

```python
from etchmem import AsyncEtchMem

async with AsyncEtchMem("http://localhost:8000") as mem:
    await mem.remember("...", source="agent-33", scope="sales")
    hits = await mem.recall("what did Acme sign?")
```

---

## API surface

The SDK mirrors the seven REST endpoints one-to-one:

| Method | Endpoint | Returns |
|---|---|---|
| `remember(data, *, source, scope, extract_mode="deferred", metadata=None)` | `POST /remember` | `RememberResult` |
| `recall(query, *, scope=None, source=None, top_k=5, include_signals=True, as_of=None)` | `POST /recall` | `RecallResponse` (iterable of `RecallResult`) |
| `sleep()` | `POST /sleep` | `SleepResult` |
| `export()` | `POST /export` | `ExportResult` (list of `Etch`) |
| `history(etch_id)` | `GET /etch/{id}/history` | `History` (iterable of `EtchVersion`) |
| `stats()` | `GET /stats` | `Stats` |
| `health()` | `GET /health` | `Health` |

All responses are plain dataclasses — see `etchmem/models.py`.

### remember

`extract_mode="immediate"` marks the signal urgent (claims extracted on the next worker tick); `"deferred"` (default) batches it cheaply. Deposits are idempotent — identical content returns `stored=False`.

### recall with time-travel

Pass `as_of` (ISO-8601) to recall what the system believed at that moment — for auditing decisions or incident forensics:

```python
hits = mem.recall("Acme contract value", as_of="2026-06-01T00:00:00Z")
```

### sleep

The server consolidates on its own cadence. `mem.sleep()` forces one pipeline tick now (batch → extract claims → fold into etches) — useful in tests and demos:

```python
tick = mem.sleep()
print(tick.etches_formed, tick.etches_updated, tick.contested)
```

### history

Every belief change writes an immutable version snapshot:

```python
for v in mem.history(etch_id):
    print(v.version, v.current_value, v.status, v.confidence)
```

---

## Configuration

| Parameter | Env var | Default |
|---|---|---|
| `base_url` | `ETCHMEM_BASE_URL` | `http://localhost:8000` |
| `api_key` | `ETCHMEM_API_KEY` | none (sent as `Authorization: Bearer …` when set) |
| `timeout` | — | 30 s |

You can also inject your own `httpx.Client` / `httpx.AsyncClient` via the `client` parameter (custom TLS, proxies, retries).

## Errors

All SDK errors derive from `EtchMemError`:

- `ConnectionError` — server unreachable (network / timeout)
- `APIError` — non-2xx response (`.status_code`, `.detail`), with subclasses `NotFoundError` (404), `AuthenticationError` (401/403), `ServerError` (5xx)

```python
from etchmem import EtchMem, NotFoundError

try:
    mem.history("no-such-etch")
except NotFoundError as e:
    print(e.detail)
```

---

## Development

```bash
pip install -e ".[dev]"
python -m pytest tests/
```

Releasing to PyPI: see [PIP-DEPLOY.md](PIP-DEPLOY.md).

## License

MIT
