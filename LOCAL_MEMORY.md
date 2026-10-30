# Local GPU Mem0 and seven simulated days

The selected deployment is self-hosted Mem0. On 26 October 2026 this host had an
idle NVIDIA L4 with 23,034 MiB VRAM, eight CPU cores and about 32 GB RAM. Both
memory models fit on the GPU. Conversation generation still uses native
Hermes → GPT-5.6 Terra; memory inference uses small local models.

The isolated components are:

| Component | Configuration |
| --- | --- |
| Mem0 | `mem0ai==2.2.1`, separate `.tools/mem0-venv/` |
| Conversational memory extraction / reflection | Qwen3 4B Q4_K_M, local GPU |
| Embeddings | Qwen3 Embedding 0.6B, 1024 dimensions, local GPU |
| Vector / history storage | Local Qdrant and SQLite under `.data/local-memory/` |
| Inference runtime | Portable llama-server distributed in Ollama v0.40.11 |
| Private endpoints | Loopback 11439 (generation), 11440 (embedding), 7371 (Mem0) |

These endpoints use randomly generated local API credentials. They use the
OpenAI-compatible wire protocol but contact no OpenAI memory API. Cloud keys and
proxy settings are excluded from worker environments. Telemetry is disabled.
There is no global Ollama installation, home-directory override, or startup
service. CUDA and application caches are explicitly inside this app.

Mem0 uses a compact extraction prompt suited to the local model, with a strict
`memory` JSON contract. The minimal ChatML template closes the thinking prefix;
the model does not spend its generation budget on reasoning. Mem0 owns extraction
orchestration, embedding, deduplication, storage and retrieval. Optional spaCy
entity ranking and fastembed BM25 are not installed; vector retrieval is active.

## Measured latency

Synthetic local round-trip checks measured a cold extraction of **52.906 s**,
including first-use CUDA compilation, then a warmed extraction of **0.936 s**.
Warmed semantic searches took **0.043–0.051 s**. These are small synthetic checks,
not an end-to-end performance guarantee. No hosted Mem0 account was used for a
head-to-head comparison. Local deployment was chosen for warm latency, available
GPU capacity, low marginal processing cost and the user's local-memory preference.

## Memory boundaries

Only the separate custom identity test enables this integration. The main app
and earlier manual demo keep their existing memory behavior. Existing exact
quotations and relay paths remain authoritative in the app's memory ledger.

After witnessed conversation messages are committed, a background queue passes
bounded source packets to local Mem0. A namespace hashes the app instance, event
and owning agent. The app rechecks source access, exclusions, event scope, capture
preferences and recall preferences. Old DMs, private assistant chats, unjoined
history and other agents' private notes are excluded. Source-packet metadata
accompanies extracted facts, which are labeled unverified model output. A packet
is provenance for extraction, not a claim that each paraphrase is an exact quote.

**Personal notes after conversations** is visible automatically below the
conversation area, with a separate card for each agent. The view refreshes as
background extraction finishes and also lists memories from existing events.
No query is required. Listing uses Mem0 `get_all` within each agent's namespace;
it makes no model or embedding requests. Private source visibility, exclusions
and recall settings are checked before display. The host can inspect all three
agents; other participants cannot inspect another resident's personal notes.
An optional search remains under **Search notes (optional)**. Model processing
stays local. **Retrieved notes and
bedtime reflections are not injected into Terra conversation requests.** That
maintains the existing local-memory boundary; main conversation turns still use
the agent's identity and bounded raw witnessed history. Bedtime reflection can
use its own local recall and previous reflection without exporting them.

## Seven-day before-sleep protocol

Select **Seven simulated days with before-sleep reflection** before Start.
The networking call cap then applies per simulated day, with up to seven times
that many Terra requests in the full week. Each bedtime adds three local-model
reflections: 21 for seven days. This call count is shown before starting.

1. **Awake:** agents network with freely chosen topics, partners and collaborations.
2. **Finish day and reflect before sleep:** stop/drain networking and pending local
   memory batches. Pending networking output after the stop boundary is discarded.
3. **Reflecting:** each agent receives its own bounded witnessed daily packet,
   starting identity, local recall and previous reflection. The local model writes
   takeaways, possible view changes, unresolved questions and tomorrow's intentions.
4. **Sleeping:** all three reflections are saved; the host can start the next day.
5. After day seven's reflection, the cycle is **completed**.

Networking retains the same event ID, rooms, introduction exposure and identity
baseline across days. Each reflection has its own day and owner. Points must cite
message IDs in the supplied witnessed packet; a constrained output schema and
server validation enforce that boundary. Summaries and interpretations remain
model-generated self-reports, not measurements of internal belief changes.
The starting identity is never overwritten. The host's compass observations remain
separate and are not sent to either model pipeline.

Reflection context includes at most 20 daily messages / 12,000 body characters,
four local memory results, one previous reflection, and bounded identity fields.
This is bounded recall, not a complete-day transcript. There is one reflection
per agent per day; failures stop that phase without automatic retries or stronger
model fallback. Stop discards pending reflection output. Restart never resumes
networking or reflection automatically.

If networking has already reached its call cap, a service refresh preserves the
day's awake state so the host can still finish that day and reflect manually.
It does not restart networking. Active/incomplete work is still interrupted.

The clock is logical: day 1 through day 7. **No wall-clock compression factor or
morning/night schedule has been chosen.** The host advances boundaries manually
until the human-time to agent-time mapping is calibrated after testing.

## Commands

From `residency_app/` on this configured host:

```bash
python3 -B scripts/local_memory.py start
python3 -B scripts/local_memory.py status
python3 -B scripts/local_memory.py benchmark  # synthetic local calls only
python3 -B scripts/identity_test.py start --port 7360
```

`start` reports `starting`; wait until `status` reports `ready`. First model load
can compile CUDA kernels. Both launchers refuse to adopt an unrelated process.

```bash
python3 -B scripts/identity_test.py stop
python3 -B scripts/local_memory.py stop
```

The app-local portable runtime archive SHA-256 is
`7bedab90dd122661be78798e9f0edf37fccf0cccf2699d2c58ea1a3afdc04b6d`.
The Qwen3 4B GGUF SHA-256 is
`3e4cb14174460404e7a233e531675303b2fbf7749c02f91864fe311ab6344e4f`;
the embedding GGUF SHA-256 is
`06507c7b42688469c4e7298b0a1e16deff06caf291cf0a5b278c308249c3e439`.
Downloads were verified against official release/registry manifests. This runtime
configuration targets Linux x86-64 with an NVIDIA GPU and compatible CUDA driver.
Other machines need an appropriate local runtime; do not silently use cloud models.

Official references:
[Mem0 configuration](https://docs.mem0.ai/open-source/configuration),
[Qwen3 4B model](https://ollama.com/library/qwen3:4b),
[Qwen3 embedding model](https://ollama.com/library/qwen3-embedding),
[Ollama portable releases](https://github.com/ollama/ollama/releases/tag/v0.40.11).

## End-to-end tests

```bash
RESIDENCY_LIVE_HERMES=0 python3 -B -m unittest discover -s tests -v
python3 -B scripts/e2e_residency.py
```

The latter signs up a synthetic host over real HTTP, saves three identities,
checks the board and private values, networks through all seven simulated days,
records 21 reflections, and verifies scoped memory and graph windows. It uses
fake inference by default and a disposable database.

```bash
python3 -B scripts/e2e_residency.py --live
```

`--live` explicitly permits up to **21 real Hermes/Terra networking requests**,
plus local Mem0 extraction and 21 local bedtime reflections, using clearly
synthetic personas in a separate temporary app. It never signs up in the user's
7360 workspace or reuses old experiment accounts. Results go to
`test-results/residency-week-live.json`; no account credentials are included.

For the full browser flow, use two terminals:

```bash
python3 -B scripts/browser_fixture.py --port 7369 --identity-test --full-week
```

```bash
RESIDENCY_WEEK_TEST=1 PLAYWRIGHT_BROWSERS_PATH="$PWD/.tools/browsers" node tests/identity_browser.cjs
```

Browser tests use fake models and refuse the real signup app's port.

The completed live end-to-end check took **445 seconds**, with 21 real Terra
network calls, 35 messages, 70 completed local memory source chunks and 21 local
reflections. The day-seven phase was `completed`, semantic retrieval succeeded,
and the four-node graph/window checks passed. The user's signup workspace stayed
empty. This functional test does not establish the eventual simulation pacing.

## Markdown files and direct access

Conversation extraction also writes a private `MEMORY.md` under
`<data-dir>/agent-memory/<event-and-owner-scope>/`. Before-sleep reflections write
`REFLECTION-day-N.md` beside it. Files are written atomically with mode 600, and
folders use mode 700. Source metadata retains who witnessed each message. The
app reads the Markdown notes back and uses local Mem0 semantic ranking to select
retrieval results; it does not send derived notes to GPT Terra. The next bedtime
reads the prior reflection Markdown when present, with SQLite as a legacy fallback.

Open **My agents → Read MEMORY.md** to read or download the current agent's notes
and reflections. Notes also remain visible automatically beneath Conversations.
Owner/event access and current memory exclusions are checked again when reading
or exporting. Recall disabled means no notes are listed or returned; existing
files are preserved without reading or replacing them. No approval exception is
needed to retain that privacy control. The files are app-managed; editing memories
through the UI is not implemented.
