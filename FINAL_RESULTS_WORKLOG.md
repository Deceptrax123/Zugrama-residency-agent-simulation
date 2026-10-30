# Final report implementation — 30 October 2026

User requested a detailed presentation/blog website of all residency results,
all agent stories, topics, flow, lineage, code/board origins, links, groups/DMs,
creative replays, and both questionnaires. Explicitly requested Stop.

- Event `5ca0be9108194c68af3b0f0d8fda0e64` was stopped through the authenticated
  host API, drained to zero workers, and frozen under
  `.data/live-residency/final-results/<event>/frozen.sqlite3` and `state.json`.
  Stored engine status `completed_with_errors`; this is a host stop with two
  prior provider errors. Do not resume networking.
- Source export `bundle.json`: three runs, 7,122 messages. Final run 2,936 messages,
  207 rooms, 21 residents, 435 Python calls, 130 boards, one chess workspace with
  11 revisions. No allowance transfers. No room reached 3 resident participants.
  A facilitator visited rooms without sending messages; include it in human
  directory metadata separately from the 21 residents.
- `residency/final_results.py` / `scripts/final_results.py`: frozen export,
  GPT-6.1 Sol High analysis, separately audited $15 estimated allowance,
  max two concurrent calls, unknown holds retained, one bounded correction of
  known completed invalid answers. No provider fallback or uncertain replay.
- Active analysis command is `python3 -B scripts/final_results.py analyze`,
  tool session 62479; output redirected to `analysis-v2.log`. It processes
  50 room batches, then 21 resident assessments, then event synthesis.
  Progress in `progress.json`, usage in `report-usage.json`; successful model
  outputs under `model/*/validated.json`. Read progress without restarting.
- First assessment packaging incorrectly yielded empty second questionnaires.
  Original builder was stopped; two uncertain holds remain protected. Valid
  first questionnaires are salvaged with exact quote validation. New builder
  independently generates and validates questionnaire 2 with all 12 explicit
  IDs in the system instruction. Final results must have 21 complete pairs.
  Nothing unvalidated has been published.
- Assessment privacy: only public starting fields and witnessed messages;
  private moral/political fields and personal notes omitted. Source excerpt
  coverage is explicit. Final presentation must record coverage separately for
  each questionnaire when a salvaged first answer used a different packet.
- `scripts/final_media.py` produces separate `presentation.json` from bundle,
  source SHA, `chess.json`, and a newly synthesized WAV of the exact four-bar
  score. Regenerate after analysis completes. Never overwrite live source logs.
- Chess: legal score 55 half-moves, Hiro–Aditya; second explicit move-announcement
  game 23 half-moves, Marina–Hiro. Both checked with chess 1.11.2 installed in
  isolated `.tools/report-libs`. No continuation invented.
- Site route `/results`, gated with existing shared observer code through
  `/api/results`. Data is uploaded by host to R2; not bundled as public assets.
  GET unauthenticated 401; host POST checks origin and bounded JSON; source
  SHA pins replacement to the same snapshot. Private keys rejected.
- Site source opened from version 23, SHA
  `2cfbba272cc731dc542f3ec526b50f88ae83ce9e`; credential in functions session
  store `resultsCredential` (renew if expired). Source opening result retained
  in chat. Need package/save/deploy existing public Site as version 24.
- UI: editorial overview, timeline network, three-run selector, all people,
  lineage/topic graph, source modals, complete rooms, chess/music/choreography,
  new labelled delayed-pitch prototype, shared task revisions, all code/results,
  boards/equations/drawings, references/research trail, both questionnaires,
  source-linked blog download, accounting/method. No agent code executes.
- Local preview session 30216 on 7396. Local R2 report uploaded, shared test code
  ABCD-EFGH-IJKL-MNOP. Own preview must be stopped at end.
- Tests: backend final report tests passed (12 distinct, inherited/imported
  discovery reports 22), Site 32 tests passed, TypeScript passed before latest
  instrument addition (session 68816 pending), browser `tests/results_ui.cjs`
  passed core gate/counts/network/replay/audio/boards/code/source navigation/
  resident/mobile flows. Latest UI additions still need recheck and final-data
  tests for actual analyses/questionnaires/lineage. Initial hydration submit
  bug was fixed by disabling form until React readiness.
- Still needed: complete analysis; repair any failed known completed answers;
  strict source/temporal/witness validation for illustrative two-hop chains;
  final aggregation/privacy/integrity verification; final data browser tests;
  production build and Site publication; authenticated R2 upload; production
  read-only QA; confirm event remains stopped. Do not finish with partial pairs.

## Current controlled report-worker drain

The report worker's private frozen `state.json` was renamed to
`state.dispatch-paused.json` (same directory) to make new report dispatches fail
closed while its two current calls finish. **The live event state was never
changed.** Tool session 62479 is the draining old report worker. Wait for it to
exit, then restore that file to `state.json` and verify its SHA against
`dispatch-pause-receipt.json` BEFORE starting the new report worker.

The new source uses three report threads (the established gateway concurrency),
interleaves agent assessments with room batches, and has a separate $25 estimated
report ceiling. Cumulative receipts and the initial $3.80 uncertain holds stay
accounted. Existing validated room/assessment results are cached and reused.
Do not kill in-flight report calls or relax the native per-call budget guard.

Latest progress before drain: 23/50 room batches, no room-analysis failures after
bounded corrections. First report process was earlier terminated for the Q2
packaging bug; two holds remain unknown. No further uncertain calls should be
introduced by this graceful drain.

Latest additional features: two verified chess replays, stop/mute delayed-pitch
prototype (explicitly a new report reconstruction), task revision history,
search trail, real deep links and transcript text search. Core browser test
passes including starting/stopping the prototype. TypeScript passes. Node tests
32 pass; backend report tests 27 pass. These counts include inherited tests.

Audit-only metadata aggregated to `audit-observations.json`: final 2,737 requests,
2,587 with nonempty derived memory, zero nonempty per-person note indexes. All
three runs use GPT-6.1 Sol. Presence of an input does not prove effective use.
Facilitator has visits but no messages; include it separately from residents.

Still implement/finish: append audit metadata + per-instrument coverage to final
presentation; strict optional two-hop assessment via `scripts/final_hops.py`
AFTER main analysis (same ledger, no simultaneous processes); deliver 42
addressed private response records if complete; actual final-data UI tests;
publication/upload/production checks. Results /api/results currently only local.

The controlled report drain completed normally. Its frozen state was restored
byte-for-byte and verified against the receipt; no new unknown holds occurred.
Current main worker is session 24831 (`analysis-v3.log`), 3 threads, $25 ceiling,
interleaved assessments and room batches. At last check: 16/21 completed pairs,
18/50 batches processed in the new schedule (27 batch caches already exist).
Do not run a second ReportModel process against the same ledger concurrently.

All older archives will now receive full chronological map/reduce interpretation
via `scripts/final_archives.py`, then their researcher resident accounts and a
cross-run blog. Run that only AFTER the main worker ends. These are researcher
accounts, not questionnaires or injected memory for the fresh final event.
Run `scripts/final_hops.py` after main and archive analysis, not simultaneously.
Both use the same cumulative $25 guarded ledger and preserve unknown holds.
Budget admission now waits for other pending calls to settle before declaring a
true cap, so parallel reservations do not prematurely cancel a feasible report.

Private result-link delivery script prepared: `scripts/deliver_final_questionnaires.py`.
It requires all 21 complete pairs, verifies stopped event, saves reviewable MD,
and inserts 42 addressed owner-scoped links. These cannot become live agent
instructions. Execute only after the shared report is uploaded and verified.
