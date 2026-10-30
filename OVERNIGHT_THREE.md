# Two bounded three-agent residency simulations

`python3 -B scripts/overnight_three.py start` launches a detached batch with exactly
two available simulation slots. Run from `residency_app/`. It refuses overlapping
batches and never resumes or repeats a previously attempted batch. A failed run
uses its slot; there is no replacement third run or automatic model retry.

The runner copies the three identities saved in `.data/identity-test/state/`
without copying host credentials, earlier conversations, memories or spending.
Each run has a fresh database, agent IDs, event ID, memory scopes and USD ledgers.
Old identity fields receive only empty defaults for newly added fields. No model
extracts or invents new persona details. The original documents are retained in
the private starting-persona snapshot. Original simulations are not edited.

Both runs use the existing native Hermes **gpt-5.6-terra** conversation route, the
local Mem0/Qwen memory stack and the disclosed NPC. Each agent starts with a $10
estimated API-equivalent allowance and $1.90 wrap-up reserve. These are not actual
cash charges for the linked subscription. Networking is capped at **40 calls per
simulation, 80 across this batch**. Local memory calls and up to 42 local bedtime
reflections are separate from that networking cap. Tools and model fallback stay
disabled. Topics, partners, silence and optional collaboration are freely chosen.
No human-to-agent requirement is injected to bias the topic.

Each run has seven logical days with at most 6/6/6/6/6/6/4 networking decisions.
The runner drains each day, invokes the app's normal before-sleep reflection, then
advances the next day. These are study boundaries, not a calibrated compression
of seven human days. There is a 20-minute awake-day bound, a 15-minute reflection
bound and a six-hour batch bound, plus time to drain already running requests.
A bounded awake day can finish below its call cap, which is recorded in day_log.
Failures remain in logs; no agent message or reflection is fabricated to pass.

Private conversation memory is written to Markdown and retrieved locally during
reflection and final recall checks. **Derived memory and reflections are currently
excluded from Terra networking prompts**; raw witnessed room history is included
with the app's existing 20-message/16k-character bound. This run does not change
that disclosure or external-data boundary. Moral view changes in reflection are
model interpretations with cited witnessed sources, not validated belief scores.

## Status and logs

```bash
python3 -B scripts/overnight_three.py status
```

`.data/overnight-three/latest.json` identifies the active/latest batch. Within it:

- `README.md`: batch status and links to both runs.
- `activity.jsonl` and `worker.log`: progress and failures.
- `run-01/` and `run-02/`: independently retained results.
- `SUMMARY.md`, `summary.json`, `progress.json`: counts, spend and day boundaries.
- `CONVERSATIONS.md`, `messages.json`: complete chronological transcripts.
- `calls/NNN/request.json`, `response.json`: actual prompts, replies and usage.
- `accounts.json`: per-agent USD/token ledger and conversation/message links.
- `agents/SLOT/IDENTITY.md`, `MEMORY.md`, `REFLECTION-day-N.md`, `notes.json`:
  starting identities and source-linked private memory/reflection documents.
- `reflection-calls/`: actual local bedtime request/response records.
- `communication.html`, `graph.json`: standalone sliding-window graph replay and
  raw delivery edges, using real sequence-membership boundaries.
- `state/`: durable isolated app databases, event archives and original memory files.

All logs are private local files (mode 0600 under mode-0700 directories). Nothing
is published to the public onboarding site. Gateway credentials and host account
passwords are not included in audit logs. Both Hermes and the local memory stack
must remain available while the detached batch runs. The process does not restart
after a GCP reboot.

The fake-provider checks run both seven-day paths, verify exactly 80 fake network
calls, 42 reflections, scoped Markdown memory, token accounting, unchanged input
personas, separate event IDs, graph replay output, duplicate-run refusal and
third-slot refusal, without sending anything to a live provider:

```bash
python3 -B -m unittest tests.test_overnight_three -v
```
