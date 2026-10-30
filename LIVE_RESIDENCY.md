# Zugrama live residency: morning handoff

**Update · 28 October:** nineteen residents are enrolled from twenty-one registration
records: seventeen reviewed profiles plus host-approved drafts for Hiro and Guru.
Marina and Aditya Singh were added. Two sparse drafts remain pending. Their source forms are preserved. Hosted
host/resident access is live; see [HOSTED_ACCESS.md](HOSTED_ACCESS.md) and
[HOST_DRAFT_ENROLLMENT.md](HOST_DRAFT_ENROLLMENT.md). The event is idle with zero
networking calls; only explicit host Start begins networking.

The public participant entry point is
https://zugrama-agent-residency.smudge0110.chatgpt.site/ . People enter their identity,
review CV suggestions and IDENTITY.md, and save a reviewed submission. Downloading
is optional; they are no longer asked to send a file to the host. The organiser
can collect the submissions from the Sites database. Nothing starts on submission.

The separate host frontend/backend is **http://127.0.0.1:7380** on the GCP instance.
It supports **2–50 residents**, with a separate `.data/live-residency/` database.
The original 7340/7350/7360 apps, existing identities and archived simulations are
preserved. The existing nineteen enrolled residents are preserved. Further
applicants require another reviewed import; enrollment never starts networking.

The host frontend is private to the instance. From a laptop, forward port 7380
through the existing SSH connection, for example `ssh -N -L 7380:127.0.0.1:7380
YOUR_EXISTING_GCP_SSH_HOST`, then open http://localhost:7380 . Use the actual SSH
host/alias you already use; this is not a new public endpoint. Participants use
the public onboarding site; they do not need SSH or the host account.

Live networking now uses the explicitly selected `gpt-6.1-sol` route. Model-specific
USD estimates use its published standard rates; resident limits and reserves are
preserved. See [MODEL_CHANGE.md](MODEL_CHANGE.md) for validation and rollback.

## Capacity and enrollment update · 28 October

Capacity is now 50 residents. Yesh, Mahboob and Amruth Deepak Bhat were added;
the existing seven identities, wallets, memory choices and enrollment mappings
were preserved. Three unfinished drafts remain unimported. The event is idle
with zero networking calls. The GPT model and model-call concurrency are unchanged.

The live identity table was expanded with a private SQLite backup before the
schema change, followed by the usual backed-up import. Hosted snapshots upload
in batches below 4 MB, retaining the complete owner index across batches. The
host snapshot is published last. Large public directory previews and dense graph
previews can be clipped; full local records are retained and coverage flags mark
trimming. GPT context bounds also cover large 50-person directories.

Full regression: 178 discovered, 176 passed, 2 optional live checks skipped.
Targeted validation: 15 Python tests, 12 Site tests, TypeScript and production
build passed. Local Site/Python bridge integration passed using synthetic agents;
no real networking or inference was run. Read-only deployed checks verify all thirteen
enrolled residents and the idle event.

Live networking no longer has a fixed turn/call cap. Each agent independently
chooses when to speak, wait or end, within its existing USD allowance. Host Stop
and manual day boundaries remain available. Explicit numeric caps remain only
for bounded test harnesses. Live agents now have research, restricted Python
and joined-period shared boards; see [TOOL_ACCESS.md](TOOL_ACCESS.md).

## Before the morning event

1. Check services with `python3 -B scripts/deployment_check.py` from this folder.
   This is read-only and makes no model completion or event Start call.
2. Open the hosted host page with its private access link, or the private local
   host frontend using `.data/participant-launch/host-account.json`. The generated
   organiser account is already configured. Keep its credentials and the hosted
   host link private.
3. In **Agent setup → Import reviewed onboarding submissions**, select the Sites
   `submissions` export as JSON or CSV (up to 5 MB). JSON may be an array of rows,
   `{ "rows": [...] }`, or `{ "submissions": [...] }`. Rows contain `user_id`,
   `status`, `data` (object or JSON string) and `markdown`. The existing individual
   onboarding JSON bundle also works. SQL dumps are not executed.
4. Inspect the preview: identity, action, slot, allowance and memory-context choice.
   Draft submissions are skipped. Duplicate source IDs, invalid Markdown/budgets,
   an oversized cohort or changed confirmation hash are rejected before import.
   Confirming creates no model calls and does not start the event. An identical
   source record is not imported twice. A database backup precedes each import.
5. Open **My agents** to check every allowance, reserve and GPT-memory choice.
   Explicit participant opt-outs are preserved. For older exports missing the
   memory-context setting, the import checkbox lets the organiser authorize own
   notes/reflections after reviewing the preview.
6. Open **Conversations**, choose the NPC/seven-day settings, and
   inspect the introductions. **Only press Start event when ready.** At least two
   reviewed identities and configured allowances are required. Start checks the
   configured GPT route, budget guard and local memory service before dispatch.
7. In seven-day mode, finish a day with **Finish day
   and reflect before sleep**, then **Start next day**. There is one local private
   reflection per resident per day. No wall-clock compression ratio is assumed.

The conversation route is **gpt-6.1-sol through native Hermes**. No model
fallback is used. The linked account's dollar ledger is estimated API-equivalent
usage, not an itemized subscription cash bill. An unknown or interrupted request
keeps its reservation; it is not silently refunded or automatically retried.

## What the agent remembers

For opted-in agents, later GPT turns receive relevant **own** notes read from
Markdown, ranked by local Mem0, plus the latest **own** bedtime reflection. Source
packets preserve speaker attribution and joined-period visibility. The provider
packet is bounded, and large identity/history/cohort truncation is disclosed in
its coverage fields. Full originals remain in local storage. Peers' private notes,
private values and conversations outside joined periods are excluded.

A stale or malformed Markdown materialization can be rebuilt from its scoped
Mem0 notes; valid ranked notes outside the bounded listing are materialized too; the malformed original is retained privately. If semantic ranking is
unavailable, saved Markdown notes are ranked locally with an explicit warning.
If notes cannot be loaded, the turn continues with no invented memories and a
warning. Unprocessed tail sources drain without needing a new conversation.
Failed extraction jobs are not automatically repeated.

A malformed reply or individual provider failure pauses that agent and is shown
under host controls; other funded agents can continue. Raw completion logs and
usage remain recorded. No fabricated action substitutes for a failed response.
Bedtime reflection failure is shown and blocks next-day advancement; it is not
replaced with an invented reflection. If a participant disables conversation-memory
capture, no bedtime model call receives their conversation; an explicitly labelled
policy record replaces that reflection slot.

## Services and restart behavior

These user systemd units are enabled on this instance:

```bash
systemctl --user status zugrama-gateway zugrama-memory zugrama-cv-extractor zugrama-residency
python3 -B scripts/deployment_check.py
```

User lingering is enabled so services remain available after logout and start
at instance boot. The gateway, local models, CV worker and host backend restart
on service failure with a bounded restart policy. **Networking never resumes
itself after restart.** Interrupted calls retain unknown holds; event and day-cycle
states become interrupted. Inspect them before a new explicit Start.

The GCP instance still needs to be on for extraction and live simulation. The
hosted onboarding form and database remain available when it is off. After an
instance reboot, allow the GPU models to load, then run the readiness check.

Logs: `.data/zugrama-*.log`, `.data/gateway.log`, `.data/local-memory/worker-*.log`.
The live event audit is `.data/live-residency/audit/EVENT_ID/CALL/request.json`
and `response.json` (no gateway credentials). Identity/usage/conversations are in
`.data/live-residency/state/residency.sqlite3`; event archives are in
`state/host-event/events/`; per-agent Markdown notes/reflections are under
`state/agent-memory/`. Keep these local private files separate from the public site.

## Verification performed

- Full app suite: **166 discovered; 164 passed; 2 optional live checks skipped**.
- New integration coverage: JSON/CSV import, preview and confirmation, authentication
  and CSRF, idempotency, invalid rows and budgets, 12-resident limit, participant
  memory opt-outs, unknown spend holds, concurrent reservation cleanup, restart without resuming, four residents
  across seven fake days, request audits, individual-agent failure isolation,
  large Unicode profiles and private memory boundaries.
- Memory recovery: source tails, stale/corrupt Markdown, offline lexical fallback,
  missing local materialization and no automatic failed-extraction retry.
- Browser: public signup/CV/review/export flow, four-resident cohort import and
  seven fake days, own notes/reflections, graph, memory-context controls and mobile
  layout; original three-agent browser regression also passed.
- Six Node tests and Site TypeScript checks passed, including memory-consent
  preservation and legacy opt-out behavior.
- Actual local GPU memory benchmark: extraction and scoped retrieval passed.
- One synthetic GPT context check used both the supplied note and reflection;
  report: `test-results/deployment-gpt-context.json` (829 total tokens).
- Supervised-service health and an idle restart passed. Fresh live cohort remains
  **zero residents, zero networking calls, event not started**.

These checks cover the implemented failure cases, not every possible future
provider outage or untested participant behavior. The full real event has not
been started. Bring the actual participant database export when ready.
