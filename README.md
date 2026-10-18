# etchmem

**Python SDK for [etchmem-server](https://etchmem.io) — the Knowledge Consolidation Engine for AI agents.**

Compatible with **etchmem-server 0.3.1** (`aolishchuk/etchmem:0.3.1`). Fields added
after 0.0.4 (`details`, `evidence`, `event_at`, `values`, …) simply stay empty against
older servers; `signal()` needs 0.2.0, contexts and `context()` need 0.3.0.

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

### Four ways to ask

Which one you want depends on what you already know. Reaching for the wrong one
is a quiet source of wrong answers.

| You know | Method | Returns |
|---|---|---|
| the subject | `know(ref)` | every belief about it — exhaustive, ordered by property |
| the kind of belief (scope, property, subject type) | `etches(...)` | every matching belief across subjects — exhaustive, paged |
| only words | `recall(query)` | beliefs ranked by wording, `top_k` |
| words, and want what they connect to | `associate(query)` | the above **plus** each subject's full facts **plus** connected nodes |

```python
# know — you have the subject
facts = mem.know("MSM-0808")            # id or surface name; variants resolve
for e in facts.settled(min_confidence=0.6):
    print(e.property, "=", e.current_value)
print(facts.contested, "open questions")

# etches — you know the kind of belief: every QA rule, across all subjects
for e in mem.iter_etches(scope="content-qa", property="qa_rejection",
                         min_confidence=0.8):
    for d in e.details:                  # label + the author's full wording
        print(e.entity_name, "·", d.value, "—", d.detail)

# recall — you only have words. entity_id chains straight into know()
for hit in mem.recall("bathroom leaks", top_k=5):
    detail = mem.know(hit.entity_id)

# associate — words, and what they connect to
assoc = mem.associate("bathroom leaks")
for node in assoc.nodes:
    print(node["hops"], node["entity"]["name"], node["reached_via"])
```

`recall` is `ORDER BY similarity LIMIT top_k` with **no threshold** — it returns
rows whatever their score, so an empty result means an empty scope rather than a
failed search, and a returned row is not by itself evidence of a match. It also
matches on the etch *narrative*, so an exact article number is compared by vector
similarity, not string equality. When you know the subject, use `know`.

`associate` follows declared relations one hop in both directions, so a fault
reached by wording leads to the part that fixes it — which shares no word with
the query.

### Async

```python
from etchmem import AsyncEtchMem

async with AsyncEtchMem("http://localhost:8000") as mem:
    await mem.remember("...", source="agent-33", scope="sales")
    hits = await mem.recall("what did Acme sign?")
```

---

## API surface

The SDK mirrors the REST endpoints one-to-one:

| Method | Endpoint | Returns |
|---|---|---|
| `remember(data, *, source, scope, extract_mode="deferred", metadata=None, occurred_at=None, context=None, context_parent=None)` | `POST /remember` | `RememberResult` |
| `recall(query, *, scope=None, source=None, top_k=5, include_signals=True, as_of=None, as_of_basis="ingest")` | `POST /recall` | `RecallResponse` (iterable of `RecallResult`) |
| `know(ref, *, as_of=None, entity_type=None, as_of_basis="ingest")` | `GET /entity/{ref}/etches` | `Knowledge` (iterable of `Etch`) |
| `associate(query, *, scope=None, top_k=5, hops=1, as_of=None, min_score=0.15, as_of_basis="ingest")` | `POST /associate` | `Association` |
| `etches(*, scope=None, property=None, entity_type=None, status=None, min_confidence=None, limit=500, offset=0)` | `GET /etches` | `EtchList` (one page of `Etch`; `.total`, `.has_more`) |
| `iter_etches(*, page_size=500, **filters)` | `GET /etches` (all pages) | iterator of `Etch` |
| `sleep()` | `POST /sleep` | `SleepResult` |
| `export()` | `POST /export` | `ExportResult` (list of `Etch`) |
| `history(etch_id)` | `GET /etch/{id}/history` | `History` (iterable of `EtchVersion`) |
| `dossier(etch_id)` | `GET /etch/{id}/dossier` | `Dossier` (etch + versions + claims + raw signals) |
| `signal(signal_id)` | `GET /signal/{id}` | `SignalRecord` (status + subjects + claims of one deposit) |
| `context(context_id)` | `GET /context/{id}` | `ContextRecord` (a conversation's focus + its signals) |
| `stats()` | `GET /stats` | `Stats` |
| `health()` | `GET /health` | `Health` |

All responses are plain dataclasses — see `etchmem/models.py`.

### remember

`extract_mode="immediate"` marks the signal urgent (claims extracted on the next worker tick); `"deferred"` (default) batches it cheaply. Deposits are idempotent — identical content returns `stored=False`.

`occurred_at` (ISO-8601 or epoch seconds) declares when the content actually
*happened*, as distinct from when you sent it. It defaults to ingest time, and
**you must set it when loading historical records** — otherwise every signal in
a backfill carries today's date, the server's recency policy has nothing to
order by, and a 2009 answer competes with a 2022 answer as an equal.

```python
res = mem.remember(
    "Modul MSM-0808: NT-2405 is the correct supply up to revision C.",
    source="ticket-resolved", scope="innoxel",
    occurred_at="2014-03-17",
)
assert res.occurred_at_declared     # the parsed value is echoed back — check it
```

### know

Every belief about one subject, exhaustive and ordered by property. `ref` is an
entity id (`product_msm_0808`) or a surface name (`MSM-0808`, `MSM 0808`),
resolved the way ingestion resolved it, so callers never need the internal id
format. `Knowledge.settled(min_confidence)` filters to what is safe to state as
fact; `.contested` counts the beliefs the engine could not settle, which belong
in an internal note rather than a customer-facing answer.

### time travel, and which clock

Pass `as_of` (ISO-8601) to `recall`, `know` or `associate`. `as_of_basis` picks
the clock:

| Basis | Question it answers |
|---|---|
| `"ingest"` (default) | What did we **believe** then — what would this system have told a customer on that date. The question an audit or a dispute asks. |
| `"event"` | What was **true** then, by the dates on the underlying facts. |

They differ whenever a source reports late — a promotion on the 2nd that reached
you on the 20th is invisible to ingest-basis on the 10th, visible to event-basis:

```python
mem.know("john@doe.com", as_of="2026-09-10")                       # believed
mem.know("john@doe.com", as_of="2026-09-10", as_of_basis="event")  # was true
```

Event-basis is only as good as your `occurred_at` discipline: signals deposited
without it fall back to ingest time, and both bases then give the same answer.

### sleep

The server consolidates on its own cadence. `mem.sleep()` forces one pipeline tick now (batch → extract claims → fold into etches) — useful in tests and demos:

```python
tick = mem.sleep()
print(tick.etches_formed, tick.etches_updated, tick.contested)
```

### history

A version is written only when a belief actually **changes**, so six daily
enrichment runs with one real change give you two versions, not six. Each
carries both clocks:

```python
for v in mem.history(etch_id):
    print(v.version, v.current_value, v.status, v.confidence)
    print("  fact true from", v.event_at, "— we learned it", v.created_at)
```

### retracted values

From server 0.0.10 a withdrawn fact ("we no longer need CSV export") is kept, not
deleted. `current_value` lists only what is still in force; `values` lists every value
ever asserted, heaviest first, with `active`, `weight`, `last_asserted_at` and
`retracted_at`:

```python
for e in mem.know("Acme"):
    print(e.property, "=", e.current_value)
    for v in e.retracted:                       # no longer valid, but once was
        print("   withdrawn:", v.value, "at", v.retracted_at)
```

### evidence and dossier

`confidence` is built from who said it (source trust declared in the server's
`ext/*.yaml`) and how many independent sources agree. Every etch and recall hit
carries the `evidence` behind the number, so you can apply your own rule:

```python
for hit in mem.recall(paragraph, scope="content-qa", include_signals=False):
    if hit.evidence and hit.evidence.max_trust >= 0.8:
        print(hit.value, [s.source for s in hit.evidence.sources])
```

`dossier(etch_id)` answers "why does the agent believe that?" in one call: the
etch, its versions, the claims that formed it (with corroboration counts) and the
raw signals behind them. Raw signals are withheld (`signals_omitted=True`) when
the server runs with claims anonymization.

`sleep()` also reports `subject_retries`, `relations_resolved`,
`claims_unsupported` (claims the server's verify step found the signal not to
state) and the `entities` resolution counters; `stats().sources_without_trust`
lists deposit sources nobody declared a trust for.

### what a signal became

From server 0.2.0 a model first decides what each signal is *about*, then
extracts its claims, and a second reading drops the claims the signal does not
state. `signal(id)` — with the id `remember` returned — shows the result for one
deposit:

```python
res = mem.remember("As an idea, we add the links to the registration.",
                   source="slack", scope="lift")
rec = mem.signal(res.id)
if rec.extracted:
    print([s.name for s in rec.subjects])     # [] = about no identifiable subject
    for c in rec.claims:
        print(c.entity_name, c.property, c.value)
```

`status` is `new`, `batched` or `extracted`; there are no claims before
`extracted`. `subjects` is `None` until the signal is resolved, and each
`ResolvedSubject` carries the signal's own words that refer to it (`quote`) and
the model's `reason`.

### conversations: context, focus, associations

From server 0.3.0 a signal can say where it was said. Pass `context` (the
conversation: a Slack thread, a ticket's comments, a meeting) and
`context_parent` (the one around it: the channel) — plain ids you choose:

```python
res = mem.remember("By the way, this ticket is done now.",
                   source="slack", scope="lift",
                   context="slack:C0CA6:1792314791.81",   # the thread
                   context_parent="slack:C0CA6")          # its channel
rec = mem.signal(res.id)
rec.focus          # what the thread was about when it was said
rec.subjects       # "this ticket" -> the ticket that tracks the thread's feature
rec.associations   # related work it brought to mind (recorded, never claims)
rec.meaning        # a reply like "let us implement that", references spelled out
mem.context("slack:C0CA6:1792314791.81").focus
```

The server reads the signal in its conversation first: unless it clearly turns
to something else, it is about the conversation's focus. Related knowledge it
recalls is kept as `associations` with a reason — whether to flag it is yours.
Signals of one conversation are read in the order they were said; the same words
in another context are another signal. Without a context a signal is read as
before. A signal that names an existing item is about it; new work in that
item's area is a new subject with the item as an association. Agreement ("let us
implement that") turns the agreed work into requirements, and a correction ("no,
new task") retracts exactly what was recorded on the wrong subject.

etchmem only records. Whether what it recorded is enough for *your* task is
yours to decide — for example: a signal about work that produced no claims on
that work, so you ask your user which work it was, and deposit the answer as a
new signal (with the question and the original message in its text), which is
extracted like any other.

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
