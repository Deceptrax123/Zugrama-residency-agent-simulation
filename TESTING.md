# Validation record

Checked on 26 October 2026 with Python 3.12.3 and Playwright 1.64.1 / Chromium
headless shell 156. All application changes are under `residency_app/`.

| Check | Result |
| --- | --- |
| Standalone app unit tests | 119 passed |
| Standalone app HTTP integration tests | 27 passed |
| Real-browser desktop/mobile flows | 13 passed, no page errors |
| Host-event browser fixture | Passed: Start, bounded run, monitor, authorization, mobile layout |
| Custom identity browser fixture | Passed: host signup, three identities, multiple-choice values, CV review and identity download, integrated board, sliding graph, compass evidence, mobile layout |
| Full-week browser / HTTP fixtures | Passed: signup through seven days and 21 private reflections, fake inference |
| Live full-week end-to-end | Passed: 21 real Terra calls, 35 messages, 70 local Mem0 source chunks, 21 reflections; 445 s |
| Existing simulation regression suite | 143 passed |
| Existing-file SHA-256 comparison | 251 checked, zero changed or deleted |
| JavaScript syntax and Python source parsing | Passed |
| Real Hermes provider smoke tests | 2 earlier Portal/solar checks; 1 current Hermes/Terra check passed |
| Local app + real gateway | Running on loopback ports 7340 / 8642; demo on 7350; identity test with preserved completed user event on 7360 |
| Docker image build / deployed HTTPS service | Not run: Docker unavailable on this host |

The browser tests use three independent resident sessions and a disposable real
app server connected over HTTP to a synthetic Hermes contract server. They verify
onboarding, profile persistence/search, shared problem contributions, author-only
resolution controls, private DMs, private Hermes chat persistence, HTML escaping,
mobile layout/navigation, and logout/login. The screenshots in `test-results/`
contain synthetic test residents and a **test gateway**, not live provider output.

The gateway contract tests verify server authentication, payloads, full successful
history, distinct resident session IDs and memory-scope keys, public-context
selection, private-data exclusions, unavailable/auth-failing gateways, timeouts,
malformed output, incomplete/cancelled turns, and enabled-tool refusal. Concurrency
tests exercise a blocked inference while another resident contributes a problem.

The isolated host installation is Hermes v0.22.5 at upstream commit
`bf0203a794a07aac3ff764972ab9087baa4e4f4e`, using its own Python 3.14.9 runtime.
The user completed Nous Portal device authorization. Two live tests passed in
63 seconds: a direct adapter request and a synthetic account making a request
through the app's real HTTP assistant endpoint. Responses contained the requested
verification sentences; the HTTP-path test also checked durable completed-turn
state. These tests used `upstage/solar-mini4:free` only. No GPT-6.1 Sol call was made.

Host tooling adds tests for credential-environment isolation, private config-file
permissions, literal environment parsing, secret preservation on reinitialization,
missing-runtime handling, and refusal to signal an unrelated process at a stale PID.
The gateway configuration has no stronger-model fallback chain. The user requested
weaker models for testing and GPT-6.1 Sol only upon explicit request.

The Dhun context update adds two transport checks: `USER.md` is supplied as shared
background and reloaded on later requests, and a missing context file prevents an
inference request. The full offline suite now passes 43 tests, with the two opt-in
live tests skipped in that run. No model calls were made for this context-only
update. The previously successful live tests above predate the context update.

`IDENTITY.md` is a sourced design draft covering the five identity layers and the
moral-compass addition. Individual identity storage, editing, and questionnaire
administration are not implemented by that document.

The voluntary co-working update adds an HTTP collaboration test and a browser
flow in which residents share Python code for a music tool, then contribute a
multiline pseudocode revision. Checks cover stored text/indentation, authorship,
shared context supplied to Hermes, fenced code rendering, escaped script content,
and mobile layout with code blocks. The offline suite passes 44 tests, with the
two opt-in live tests skipped. No model calls or code execution were used for
this update. The prompts explicitly allow producing code and solution drafts
while distinguishing drafting from execution or deployment.

The app and gateway run under a detached local supervisor; no global launcher,
shell profile, or system startup service was installed. External HTTPS hosting is
not configured. Follow `README.md` for local access and lifecycle commands.

The original repository already had an untracked `sites/` directory. It was left
untouched. No existing app code, simulation configuration, persona, report, or saved
workspace file was changed. Disposable test servers were stopped after validation;
the actual app and its dedicated Hermes gateway are left running.

The conversational-memory update adds 16 unit tests and two HTTP integration
tests. The complete offline suite discovered 64 tests: 62 passed and two opt-in
live-provider tests were skipped. After final validation hardening, all 29 memory
and HTTP integration tests passed again. Eleven desktop/mobile browser flows
passed, including source selection, saved priorities, pin/hide/search, and the
Ada → Bob → Eve relay. Tests verify that Eve cannot inspect Ada and Bob's original
private message and that local memory does not enter the existing Hermes payload.
Other checks cover forged sources/quotes, owner isolation, category weights,
exclusions, exact duplicate consolidation, alternate wording/evidence retention,
contradictory statements, draft labels, bounded batches/recall, concurrent jobs,
and failure handling without automatic retry.

No real model calls were made for conversational memory. Extraction uses local
rules and recall uses SQLite/FTS5; model-based semantic extraction and private
memory recall in Hermes are not enabled. See `CONVERSATIONAL_MEMORY.md` for these
limits. The user subsequently chose to keep memory local. JavaScript syntax and
all 18 app Python source files passed parsing checks. The original 251-file
checksum manifest was rechecked: no changed or deleted files. A private SQLite
backup was made before restarting the isolated app/gateway; both are healthy on
ports 7340/8642. The disposable browser fixture was stopped.

The chosen default focus is now interests, skills, ideas, commitments, stated
priorities, and disagreements, all at High (2). An explicit priorities category
and local phrase rule were added. Two additional unit tests check that focus and
compatibility with saved policies that lack the new category. All 31 memory/HTTP
tests passed after this change. Existing saved category weights, instructions,
and exclusions are retained; new categories receive defaults without overwriting
personal settings. No provider extraction or private-memory payload was enabled.

The previous-persona trial harness was prepared without running an experiment.
Eight offline harness tests passed with subprocess launches explicitly blocked.
They check exact experiment-2 starting profiles, idle preparation, isolated trial
paths and credentials, per-person conversation scope and two-hop attribution,
memory-off context, JSON action validation, explicit Terra/tool settings, and
frozen-input integrity. The `plan` command was checked and reported zero model
calls. No permanent trial directory was created. The old 251-file checksum
manifest was rechecked with no changes. Model availability, live trial generation,
and the optional trial viewer were not exercised; the user requested setup and
run commands only. See `experiments/previous-nine/README.md` for commands and limits.

The introduction/joined-conversation update adds public one-time introductions,
joined-period transcript visibility, start/join/send/leave actions, and automatic
local memory capture. The offline suite discovered 85 tests: 83 passed and two
opt-in live-provider tests were skipped. This includes nine conversation unit
tests, nine offline persona-harness checks, and 14 HTTP integration tests. Checks
cover nonparticipant read/write denial, source/memory isolation, identical-time
and concurrent join boundaries, leave/rejoin gaps, idempotent joins, action
rollback, public board access, exact relay evidence, and capture preferences.
After the final capture-switch isolation fix, all 41 conversation/memory/HTTP
tests passed again; all nine persona-harness checks also passed after verifying
the model prompt excludes pre-join messages. Disabling joined-conversation capture
is respected even when legacy DM batch extraction is enabled.

Thirteen browser flows passed with no page errors. New flows verify the shared,
escaped introduction board and a third resident joining/leaving a conversation:
both the transcript and memory exclude pre-join text and absence gaps, while an
accessible relay produces Ada → Bob → Eve attribution. One initial browser
assertion counted board cards before an asynchronous refresh completed; it was
changed to wait for the third card and the fresh-fixture run passed. Mobile
navigation includes both new views. All 21 app Python files and JavaScript syntax
passed parsing checks. The original 251-file checksum manifest remained unchanged.

New persona preparations use protocol 2: nine introductions before networking,
one full board exposure per persona during networking, and explicit room
start/join/send/leave actions. The 27-call total includes nine introduction calls.
`plan` was checked without creating a trial. No experiment, real model request,
or provider extraction was run for this update. Old trials are retained and
require a new preparation name to use this protocol. Storage migrations are
additive; the isolated live database was backed up before reload. See
`CONVERSATIONS.md` for the resulting access and memory rules.

The manual three-resident setup adds four offline setup/configuration checks and
one Hermes transport check for explicit Terra advertisement and fresh session
scopes after a model change. The full offline suite discovered 90 tests: 88 passed,
two opt-in live tests skipped. The dedicated real Hermes gateway was then switched
to `openai-codex` / `gpt-5.6-terra`, using its supported import of the already linked
account into the isolated auth store. Its native runtime remains active; gateway
tools, global memory, background review/title generation, and fallback models
remain disabled. The app verifies the exact advertised model route before calls.

One short synthetic connection test passed through the real Hermes→Terra path
in 2.5 seconds using a disposable database. The manual demo was launched on port
7350 with three fictional resident logins, three public introductions, and eight
locally selected memory notes per resident. HTTP verification confirmed all logins,
the Terra route, and zero initial assistant turns/external memory processing.
Independent browser sessions verify each login, introduction board, local memory,
and the Terra connection label without submitting model requests. No autonomous
worker or networking experiment was started. See `DEMO_THREE.md` for access and
lifecycle commands. Configuration backups were retained under `.data/backups/`.

The host-started event adds nine offline unit tests and one HTTP integration test.
The full suite discovered 100 tests: 98 passed and two opt-in live tests skipped.
Coverage includes idle startup, introduction gating, host-only control and CSRF,
concurrent workers with a global request limit, Stop discarding in-flight output,
failure without retries, interruption after restart, local capture, and privacy.
The host can inspect event conversations without giving that operator feed to
its own persona's model context. Prior manual history and derived notes remain
excluded from event requests. All 26 Python files parsed and JavaScript syntax
passed. A disposable browser fixture exercised the actual UI against a fake
gateway, including a one-call event, host-only monitoring, and mobile layout.
These tests made no real model calls. The live demo is left idle for the host.

To reproduce the host-event browser check, run these in separate terminals from
this folder (with Playwright installed as described in `README.md`):

```bash
python3 -B scripts/browser_fixture.py --port 7359 --host-event
```

```bash
RESIDENCY_TEST_URL=http://127.0.0.1:7359 PLAYWRIGHT_BROWSERS_PATH="$PWD/.tools/browsers" node tests/host_event_browser.cjs
```

The browser check refuses ports other than 7359 and 7349, so it cannot press Start
on the live demo at 7350. Stop the disposable fixture after the check.

The custom identity test adds nine unit tests and two HTTP integration tests.
The complete offline suite discovered 111 tests: 109 passed and two opt-in live
tests skipped. Twenty identity/event/HTTP checks passed again after hardening
event archives and preserving graph labels from starting identities; the two
identity HTTP checks passed after making the test host an observer. Identity
editing is blocked while workers run; human revisions and event-start baselines
are separate. Private moral/political descriptions reach only the owning agent's
request unless explicitly shared. Host audit data and compass observations never
enter model context. Ordinary manual-demo behavior remains separately covered.

New graph tests verify directed delivery counts across time windows, exact join
boundaries, leave/rejoin gaps, exclusion of older rooms, finite query parameters,
and host authorization. NPC tests verify no access to pre-join agreement, multiple
speakers, qualified-agreement exclusions, witnessed attention concentration,
cooldowns, and private intervention-audit isolation. Compass tests require exact
quotes from a current-event agent message and preserve the starting identity.

All 33 Python files parsed; JavaScript syntax passed. Existing 13 desktop/mobile
browser flows and the earlier host-event browser flow passed. The new identity
browser flow passed against a disposable fake model, including all three profiles,
private values, explicit Start, an integrated four-introduction board, a four-node
graph, time-window selection, replay scrubbing, evidence-linked reconsideration,
and mobile layout. An initial control-label issue was corrected with explicit
labels; the replay check now waits for the selected window and uses native slider
keys. Scrubbing updates on release, avoiding replacement of the slider mid-drag.

The real custom app is left empty for the user's signup, with zero personas,
conversation messages, assistant turns, or study observations. No live event or
provider call was started for this update. The earlier demo had a user-started
run that stopped after 12 requests / 9 completed calls because of an invalid room
reference. Its 15 messages and failure state were preserved and backed up before
reloading. The new prompt supplies explicit valid IDs and distinguishes starting
a room from messaging an existing one; this change has only offline validation.
See `IDENTITY_TEST.md` for commands, disclosure rules, and current limitations.

The local-memory update adds five offline tests; the final suite discovered 116
tests: 114 passed and two opt-in live-provider tests skipped. The five new checks
passed again after hardening background queue shutdown. Tests cover local-only
transport, per-agent/event memory namespaces, witnessed-source boundaries, capture
preferences, forged reflection citations, seven manual day transitions, preserved
event/room/identity state, once-per-agent bedtime records, authorization and no
automatic resumption after restart. All 39 Python sources parsed; JavaScript
syntax passed.

The disposable browser test exercised signup, all three identity forms, private
values, explicit Start, the integrated board, graph windows and scrubbing, quoted
compass observations, all seven bedtime/next-day transitions, and mobile layout.
It used fake conversation and memory inference. A separate HTTP full-week test
also passed with 21 fake network calls and 21 fake local reflections in 3.67 s.

After the user's request for a full end-to-end test, a separate temporary app ran
the real Hermes/Terra route with synthetic personas and the GPU-backed local Mem0
service. All seven days passed. The bounded run made exactly 21 network requests,
stored 35 conversation messages, completed all 70 witnessed source-chunk jobs,
and generated 21 evidence-checked private local-model reflections. It completed
in 445 s. Final semantic retrieval and a four-node directed graph passed; the
window at event offset zero was empty. The report is
`test-results/residency-week-live.json`. This is a synthetic functional test,
not validation of psychological state measurements or a calibrated week of human time.

The host has an NVIDIA L4 with 23,034 MiB VRAM, eight CPU cores and approximately
32 GB system RAM. Small local Qwen extraction and embedding models were selected.
The final runtime loads both onto the GPU; no global model installation or cloud
memory service was enabled. Mem0 telemetry is disabled. Synthetic measurements
were 52.906 s cold extraction, then 0.936 s warmed extraction and 43–51 ms warmed
retrieval. Hosted Mem0 was not benchmarked. See `LOCAL_MEMORY.md` for configuration,
the compact extraction prompt, logical clock, model provenance and limitations.

The user's 7360 signup workspace was backed up and reloaded with local Mem0 and
the seven-day controls. It remains empty: no host account, agent identity, message,
reflection or Mem0 source was created there by testing. The original 251-file
manifest was checked again with zero changed or deleted files. Existing apps and
the dedicated Hermes gateway remain available. Private memory and reflection
records continue to be excluded from Terra conversation context.

## CV identity extraction and multiple-choice values

The complete offline suite discovered 121 tests: 119 passed and two opt-in live
provider tests were skipped. Four new unit tests and one HTTP integration test
cover CV bounds, allowed identity targets, exact supporting quotes, rejected
fabrication and truncation, the unchanged local model endpoint, preview without
saving, host-only access, accepted-evidence persistence, and five-pillar export.
The seven focused tests passed again after adding multiple-choice options.

The disposable full-week browser flow passed with fake inference: signup, three
identities, multiple-choice moral/political answers, local CV suggestions, explicit
acceptance without replacing existing fields, persisted skills, IDENTITY.md
download with quotes, seven days of networking/reflections, graph and mobile layout.
No page errors occurred. The fixture was stopped afterwards.

One synthetic CV was then tested through the real local Qwen3 4B service and a
disposable HTTP signup app. Extraction, review-style save, and identity export
passed in 2.45 seconds, producing five suggestions. No Terra requests or real
networking event were started. The report is
`test-results/identity-cv-local.json`. The running signup app was refreshed while
idle, preserving its existing host account and empty agent slots; the same local
models and conversation-model configuration remain in use.

## GPT CV extraction update

CV extraction now uses the configured GPT-5.6 Terra model through Hermes. The
local-Qwen CV implementation and its measurements above are historical.
Conversational memory and bedtime reflection retain their separate local models.
The UI discloses the external CV request; extraction does not include saved
identities, resident conversations, or local memories. Each CV request has its own
Hermes session, and invalid responses fail without a retry or Qwen fallback.

All seven focused unit/HTTP checks passed, including model-route refusal, fresh
sessions, bounded CV-only payloads, exact quotes, incomplete-response handling,
private host access and retained evidence. The full-week fake-inference browser
flow also passed. One synthetic CV through the real GPT route passed in 3.451
seconds with five suggestions, one GPT request, zero Qwen CV requests, and no
networking event. Report: `test-results/identity-cv-gpt.json`.

## PDF CV uploads

The complete offline suite discovered 125 tests: 123 passed and two live-provider
tests were skipped. Three PDF unit tests exercise actual multipage extraction,
invalid/oversized/empty/overlong documents, page limits and parser timeouts. One
new HTTP integration test covers host authentication, CSRF, PDF-to-text-to-GPT
transport, no automatic identity save, and rejection before inference.

The full-week disposable browser flow passed with all three agents uploading
synthetic PDF files, automatic suggestions, preserved identity drafts, accepted
evidence, identity export, networking controls and mobile layout. One synthetic
PDF also passed through the actual GPT-5.6 Terra route in 1.899 seconds, yielding
two suggestions. No networking event was started. Report:
`test-results/identity-pdf-gpt.json`. The PDF parser is app-local pypdf 6.21.2; no
global packages or conversation-model configuration changed.

## Editable identity review before onboarding

The complete offline suite discovered 129 tests: 127 passed and two opt-in live
provider tests were skipped. Three new document tests cover the five pillars,
public introduction, disclosure, Unicode/embedded Markdown round trips, human
corrections, removal of stale CV evidence, and rejection of broken structure or
missing required fields. One HTTP test verifies preview creates no agent or public
introduction, submission saves the edited values and document/revision, download
matches the submitted file, CSRF/host isolation, and zero provider requests.

The full-week browser fixture passed: three PDF uploads, editable IDENTITY.md
review, no agent before submission, human edits applied through Back to form,
per-slot draft retention, final submission/download, and the existing networking,
graph and sleep controls. Additional browser assertions cover the editor on mobile
and discarding a damaged document without losing the form. All inference in this
flow is fake. No real provider request or user event was started for this update.

The idle signup backend was refreshed after a private database backup. Existing
host account and empty agent slots were retained. Reviewed documents are stored
additively alongside identity/revision records; existing identities retain their
previous export behaviour. The 251-file original-simulation checksum comparison
remained unchanged.

## General-purpose CV interpretation

The exact-quote/strict-output gate was removed after a user reported the
unsupported-CV-evidence error. GPT still uses the configured gpt-5.6-terra route.
Quotes are optional model context, not verified evidence. Missing excerpts, PDF
line-break differences, additional metadata, unfamiliar categories, larger entry
counts and narrative output remain reviewable. Broader context is retained in
Other CV context, including the editable IDENTITY.md and agent identity.
No handwritten skills vocabulary or village-topic matching determines eligibility.

The complete offline suite passed: 129 discovered, 127 passed, two opt-in live
provider tests skipped. Updated unit/HTTP cases cover the previous quote-mismatch
rejection and flexible responses. The full-week browser fixture passed with
non-verbatim excerpts and an unfamiliar category, including PDF upload, review,
human correction, submission, download, mobile layout and existing event controls.
A synthetic interdisciplinary CV PDF also passed the real Terra extraction,
identity review and isolated submission in 6.859 seconds with nine suggestions.
No user event was started; the report is test-results/identity-general-cv.json.

The user's idle signup app was refreshed after a private backup. Its host account
and empty agent slots were preserved. Existing identity documents without the
new optional CV-context section remain parseable. Original simulation checksums
remain unchanged.

## Automatic personal notes and focused CV/website extraction

The complete offline suite passed: 135 discovered, 133 passed, two opt-in live
provider tests skipped. New checks cover public webpage fetching, public-IP
pinning and redirect refusal for private addresses, HTML text extraction,
CV/website-to-GPT context, expertise/product/offer fields, raw-CV separation,
query-free note listing and host-only access. Existing memory tests also check
that automatically listed notes exclude unseen pre-join messages. A restart
check preserves a completed day's manual bedtime state without resuming work.

The full-week browser fixture passed with PDF and website extraction, named
product and subject-expertise highlights, no raw CV copied into the identity
document, human editing/submission and automatic per-agent notes without a
search. All browser inference and portfolio-page content were synthetic.
A real public webpage fetch against example.com passed independently.

One combined synthetic CV/product-page request through real GPT-5.6 Terra
produced skills, relevant project context, subject expertise and products built
in 7.329 seconds. The editable identity omitted unrelated office-job history.
The page source for this model check was a synthetic fixture. Report:
`test-results/portfolio-expertise-gpt.json`.

The real completed user event was preserved across the update: three identities,
75 messages, 149 completed memory source chunks, 40 networking calls, and day 1
awake awaiting manual bedtime. Authenticated listing returned 42, 40 and 42
existing notes with zero model/embedding requests. Identity rows, transcript rows
and memory-job rows were compared byte-for-byte with the private pre-update
SQLite backup. Report: `test-results/automatic-personal-notes.json`.
No new networking event or reflection was started. Original 251-file simulation
checksums were unchanged. Conversation and memory models remain unchanged.

## USD allowances and independent onboarding

The latest complete app run discovered **148 tests: 146 passed and 2 opt-in live
checks skipped**. New tests cover currency precision, atomic concurrent holds,
unknown usage, usage before invalid-action rejection, individual wrap-up,
private owner-to-agent requirements, conversation attribution, scoped Markdown
export/retrieval and review-only onboarding imports. No model type changed and
no live networking experiment was started for this update.

The new **My agents** browser check passed allowance editing, independent token
ledgers, private requests, memory read/download and a 390px mobile layout. The
existing complete signup/three-agent/seven-day browser check also passed with
fake inference only.

The separate **Zugrama onboarding site** passes TypeScript checking and a
production build. Its local browser flow passed ChatGPT mock sign-in, durable
D1 draft save/reload, R2 PDF upload, all identity/MCQ fields, editable Markdown,
USD/memory preferences, private export, missing-auth/CSRF checks and mobile layout.
The resulting actual export imported into an empty app agent slot in a second
browser fixture without starting an event or making a model call. Production
publication succeeded, the live `submissions` table was verified through Sites,
and the published landing page returned HTTP 200 in Chromium with the Zugrama
title and ChatGPT sign-in link. Live interactive ChatGPT sign-in was not automated.
All 251 original simulation files still match their original SHA-256 hashes.
The real user event retains 3 identities, 3 identity revisions, 75 messages,
149 memory source records, 40 calls and its original starting identities.

## Account-free Zugrama onboarding

The complete app suite discovered **149 tests: 147 passed and 2 live tests skipped**.
Three Node tests also passed for private-key generation, validation and hashed
storage IDs. Browser checks passed direct name/nickname entry without accounts,
saved-draft reload, return-link recovery in another browser, isolation between
people with the same name, private PDF/export/delete, MCQs, review, USD/memory
preferences, Origin enforcement and mobile layout. The exported nickname also
imported and saved successfully in an isolated residency fixture. Existing
IDENTITY.md documents without a nickname remain compatible. No model calls or
networking experiment were started for this update.

The account-free update was published as Site version 2. A fresh anonymous
Chromium visitor on the live URL receives HTTP 200, opens a private draft
without sign-in, and sees Name and Nickname with no email/password fields.

## Hosted CV extraction on Zugrama

The app suite discovered **153 tests: 151 passed and 2 opt-in live checks skipped**.
New worker tests cover isolated CV-only processing, fixed Terra routing, local PDF
errors, host daily limits, uncertain callback delivery and prevention of repeated
model execution. Five Site Node tests passed, including general-purpose suggestion
adaptation and append/deduplication without discarding typed answers. TypeScript
checking and production packaging passed.

The local onboarding browser flow passed PDF upload, queued extraction through a
synthetic authenticated worker, skills/expertise/product suggestions appearing in
the editable form, IDENTITY.md review, final export, no sign-in and existing privacy
checks. The local queue API integration passed worker authorization, Origin checks,
concurrent enqueue deduplication and exclusive claim, resident isolation, fixed
model enforcement, completed-result reuse, explicit retry, stale PDF rejection and
cascade deletion. No provider calls occur in those local tests.

Published **Site version 3** passed a separate live check with one synthetic PDF
through the actual unchanged **gpt-5.6-terra** connection. Three suggestions reached
the website, the typed skill was preserved, and the reviewed identity was saved.
The synthetic submission, its PDF and extraction jobs/results were then deleted.
The host's outbound-only extraction worker remains running; it must be restarted
after a host reboot, along with Hermes. No live networking event was started.
All 251 original simulation files still match their SHA-256 baseline.

Local checks (Site preview on 5175; `.dev.vars` must contain the synthetic token
`EXTRACTION_WORKER_TOKEN=qa-extraction-worker-only`; apply migrations first):

```bash
# In residency_app/onboarding_site (Node >=22.13)
node --test tests/submission-key.test.mjs tests/cv-extraction.test.mjs
node node_modules/typescript/bin/tsc --noEmit

# In residency_app, with the existing browser dependencies available
python3 -B -m unittest tests.test_intake_extractor -v
PLAYWRIGHT_BROWSERS_PATH="$PWD/.tools/browsers" node tests/onboarding_site_browser.cjs
node tests/onboarding_extraction_api.cjs
```

The standalone `tests/onboarding_live_cv.cjs` is opt-in via `RESIDENCY_LIVE_CV=1`;
it calls the real model and published Site using synthetic data, then deletes that
synthetic submission. It is not run by unit tests or local browser tests.

## Live small-cohort readiness · 27 October 2026

The final complete suite discovered **166 tests: 164 passed, two opt-in live tests
skipped**, in 116.014 seconds. The fake-provider integration path exercised four
residents for all seven days with own-note GPT context and prior reflections.
Additional checks covered import review/idempotency/invalid exports and allowances,
participant opt-outs, maximum-size Unicode identities, individual reply failures,
unknown spend and no-resume restart recovery, and concurrent reservation cleanup.

Memory regressions verify tail-source drainage without needing a new message,
scoped access, stale and malformed Markdown recovery, offline lexical ranking,
missing local notes and non-retry of failed extraction. A private source belonging
to another agent is excluded from both local recall and provider context.

Both host browser flows passed: the new four-resident cohort interface and the
existing three-agent interface, including seven fake days, notes/reflections,
sliding graphs, editable identities and mobile layout. Browser polling explicitly
waits for the persisted transition phase. Public onboarding passed local browser
checks with explicit own-note GPT preferences. Six Node tests, TypeScript checking
and production Site packaging passed. Version 4 was published successfully.

Live checks were limited to infrastructure and synthetic input: local GPU Mem0
extraction took 1.076 s and recall took 0.070/0.054/0.049 s; one actual GPT Terra
request consumed the provided memory and reflection topics (829 total tokens).
No real residency event was started. Service health and a fresh host-app restart
passed with zero enrolled residents and zero networking calls. All four user
systemd services are enabled and active, with lingering enabled for logout/boot.
The L4 reported 9,088 MiB of 23,034 MiB used and the data filesystem had 465 GB free.

All 251 original simulation files retained their SHA-256 baseline. The previous
three-agent event and its identity, transcript and usage counts stayed unchanged.
The real participant database remains unimported, as requested.

**Later update · 28 October:** the user subsequently authorized enrollment and
protected hosted access. Seven reviewed profiles are imported, three drafts were
skipped, and the real event is still idle. Site version 6 passed the new resident /
host access checks; see [HOSTED_ACCESS.md](HOSTED_ACCESS.md). The complete suite
now discovers 171 tests, with 169 passed and two optional live checks skipped.

See [LIVE_RESIDENCY.md](LIVE_RESIDENCY.md) for the tested import schema, host access,
explicit morning Start sequence and remaining operational boundaries. Evidence:
`test-results/deployment-readiness.json`, `deployment-gpt-context.json`,
`cohort-browser.png`, `identity-host-desktop.png` and `onboarding-live-readiness.json`.

A further focused retrieval regression passed for a ranked note outside Mem0’s
bounded listing: it is persisted into the event-scoped Markdown document and
returned, rather than silently discarded. Capture-disabled residents are also
tested to receive no bedtime model call; their reflection slot is explicitly
labelled as a policy record.

## Morning workflow recheck · 27 October 2026

The full Python suite discovered **167 tests: 165 passed, two opt-in live checks
skipped**, in 116.814 seconds. Eight Site Node tests and TypeScript checking passed.
An additional 12 cohort/memory tests passed after strengthening the audit checks:
all 28 request/response pairs in the synthetic seven-day event reconcile with the
resident, call number, token ledger and conversation-context links. Audit files
have mode 0600 and contain no gateway authorization credential.

Browser checks passed the original three-agent onboarding/event interface, the
four-resident cohort import and seven-day cycle, local public-form onboarding,
and the published Site's anonymous reviewed submission and memory opt-out. The
published CV smoke check also passed through actual GPT Terra with a synthetic
PDF; its submission, PDF and extraction job were deleted afterwards. One separate
synthetic GPT request correctly used both supplied memory and reflection topics
(829 tokens). No real networking experiment was started.

Local GPU memory extraction took 0.878 s; the three recall queries took
0.075/0.059/0.067 s and returned the extracted note. Recovery coverage includes
malformed/stale Markdown, unavailable ranking, missing files, bounded listings,
source provenance, per-resident access and extraction failure without retry.

For the local queue API integration use the supported development preview:

```bash
# In residency_app/onboarding_site, with Node >=22.13
# .dev.vars contains only the synthetic local worker credential:
# EXTRACTION_WORKER_TOKEN=qa-extraction-worker-only
npm run dev -- --host 127.0.0.1 --port 5175

# In residency_app, in a second terminal, after the onboarding browser check
node tests/onboarding_extraction_api.cjs
```

That API check passed authentication, Origin enforcement, concurrent queue
deduplication/exclusive claim, owner isolation, fixed-model validation, result
reuse, explicit retry, replaced-PDF rejection and delete cascade. A separate
Wrangler production-build preview reproduced a local worker-restart 503 during
this rapid authorization sequence; that run is retained as failed evidence.
The supported development preview passed without adding request retries. The
deployed Site passed its independent browser and real CV checks; the local
Wrangler behavior is not a guarantee about all hosted failure conditions.

Site version 5 adds a separately authenticated organiser operation limited to
three contribution fields. The requested Srinitish/Smudge profile update was
verified in both saved JSON and IDENTITY.md, with unrelated fields preserved and
stale-write rejection checked. A private before/after backup is retained locally.

All four deployed services are active and enabled, with zero supervisor restarts
at this check. The live cohort remains empty and unstarted. All 251 original
simulation files match the baseline, and the previous three-agent event's saved
identity, transcript, usage and event counts remain unchanged. See
`test-results/MORNING_READINESS.md` for the final handoff and evidence paths.


## Live capacity 50 · 28 October 2026

Full Python regression: 178 discovered, 176 passed, 2 optional live checks skipped
(`test-results/capacity-50-full-regression.log`). Twelve Site tests, TypeScript,
production build and local Site/Python bridge integration passed. New cases cover
backed-up capacity expansion, unchanged existing identities/revisions/mappings and
memory choices, 50-person import, rejection of resident 51, worst-case Unicode
profiles within GPT/dashboard bounds, and upload batches retaining other owners.
Read-only published browser checks verify ten residents and an idle event with
zero calls. The live configuration and SQLite capacity are both 50; no model
route or concurrency setting changed. Original 251-file baseline is unchanged.

```bash
python3 -B -m unittest tests.test_cohort_capacity -v
python3 -B -m unittest discover -s tests -v
```

## Optional person/task memory and shared live artifacts · 30 October 2026 IST

The live runtime now offers actor-bound `conversation_recall`, private revisioned
`person_note_write/read`, and shared `workspace_create/read/update` tools. They
are optional and add no extraction/model call. SQLite preserves revisions;
private Markdown copies under the state directory's `collaboration/` folder are
read, repaired when needed, and permission checked. Shared snapshots follow the
announcement's witnessed join/leave intervals. A later joiner needs an explicit
new handoff. Revision conflicts do not overwrite intervening work.

The optional `delegate` tool makes one completion on the parent's configured
model and reasoning effort, with up to three read/research/Python calls. The
parent's normal USD allowance funds it; wrap-up reserve cannot fund helpers.
Recursive delegation and shared-state/conversation writes by helpers are denied.
Every helper has a separate attributable usage entry and private request/response
audit, linked to its parent call. No model fallback or automatic retry is added.

Site version 20 retains the shared `/live` code and adds per-event tabs plus
Conversations, Code & results, Whiteboards, and Shared tasks menus. A read-only
mirror publishes only Python source/results, shared board entries and shared
workspace revisions. It never exports private person-note/recall tool arguments
or results. Artifact history is paginated and incremental publication is
idempotent. GETs trigger no analysis, model calls or event controls.

Validation passed: focused Python unit/integration cases for notes, revised
permissions, Markdown repair, witnessed gaps, long state pagination, simultaneous
updates, capture failure after commit, idempotent tools, full synthetic networking
continuation, high-effort model routing, helper quota/budget guards, recursion
rejection, and read-only artifact projection. Cohort/context/recovery/bridge and
provider-pause regressions passed. All 28 Site tests, TypeScript and production
build passed. The local browser check covers shared-code gates, old-code
revocation, message/artifact pagination, code display without execution, rendered
equations/drawings, task checkpoints, run switching, responsive layout, private
field exclusion, and absence of event-control writes. Published read-only checks
and deployment receipts are retained in `test-results/` and private live state.

Synthetic checks (no external model calls):

```bash
python3 -B -m unittest tests.test_collaboration tests.test_delegation tests.test_agent_tools tests.test_watch_artifacts tests.test_watch_bridge tests.test_sol_migration -q
```

Fresh event metadata and private deployment receipt:
`.data/live-residency/fresh-memory-event.json`. The previous event is stopped,
its transcript/audits and final metadata retained, and no questionnaire was run.
The new event uses GPT-6.1 Sol with explicit high reasoning effort, the same 21
resident identities, no call cap, and the existing $100-per-agent limits and
cumulative ledger. The memory tools aid continuity; they do not guarantee that
an agent will choose to record a useful checkpoint or avoid repeating itself.

## Resident turn fairness · 30 October 2026 IST

A live 21-person event exposed starvation in the ordinary Python semaphore:
three continuously awakened tool users could reacquire slots before residents
already waiting. Eighteen workers stayed alive, with funded wallets and no
provider error, while last-turn ages exceeded their requested 1–3 minute waits.
The limit of three concurrent turns is retained; admission now uses a FIFO queue
with cancellation cleanup. An agent's tools, chosen delays, messages and topics
are unchanged. `/api/event` includes live `turn_queue` diagnostics.

Tests passed: ordered handoff with an immediately returning busy worker,
cancelled queue heads, bounded parallelism, and a synthetic 21-agent event where
all 21 receive a turn before any worker takes a second turn. Agent tools,
helpers, restart/resume, quota pauses, event recovery, uncapped events, host
controls and SQLite concurrency regressions also passed. No live test experiment
was created. The same event was safely drained, backed up, reloaded and resumed;
21 residents, GPT-6.1 Sol High, existing room history and USD limits were retained.
Live admission/completion verification is recorded in
`test-results/turn-queue-live-verification.json`.

```bash
python3 -B -m unittest tests.test_turn_queue tests.test_agent_tools tests.test_delegation tests.test_agent_restart tests.test_provider_pause tests.test_event_recovery tests.test_uncapped_cohort tests.test_host_event tests.test_sqlite_concurrency -q
```

## Optional groups and membership observation · 30 October 2026 IST

Agents can start a group directly with `start_conversations` containing
`{"with":["resident-id","another-resident-id"],"body":"shared opening"}`.
A single string retains the existing DM behavior. A group opening creates its
own room and never merges a private DM or copies old messages into the group.
Existing rooms can still grow through voluntary joins, with no two-person cap.
The action validator accepts only distinct other residents in the current event.
No topic, grouping, group size target or recipient rotation is assigned.

Message, recall, derived-memory, board and shared-workspace visibility still
follows each resident's witnessed sequence windows. Outsiders receive only room
presence metadata. Joining does not expose earlier history; leaving excludes
subsequent messages until rejoining. Explicitly relayed claims remain possible,
with attribution, as in the original two-hop networking protocol.

Site version 21 adds a Groups menu under `/live`: Together now and Group history,
current and departed members, join/leave times, and a link to that room's human
observer transcript. It counts three or more simultaneously present residents;
a facilitator is excluded from that count. Historical visitors who never overlap
do not count as a group. The latest 100 membership changes are shown per room,
with explicit total coverage. Old snapshots without membership metadata are
labelled unavailable rather than inferred. The shared human observer code is
unchanged; private agent permissions are not expanded by the human viewer.

Tests passed for 3–6 resident rooms, direct-room separation, outsiders, late
joins, leave/rejoin gaps, boards and task states, invalid group lists, event
scope validation, and full synthetic model-driven group creation. Membership
projection covers replacements versus real groups, facilitator exclusion,
coverage limits and private-field filtering. Site unit tests, TypeScript,
production build, and local browser membership/navigation/mobile checks passed.
Published verification is recorded in `test-results/live-groups.json`.
The same active event, identities, FIFO turn admission, model effort and USD
limits were preserved; no new live experiment or forced group was created.

```bash
python3 -B -m unittest tests.test_group_conversations tests.test_conversations tests.test_watch_bridge tests.test_collaboration tests.test_agent_tools tests.test_turn_queue -q
```


## Optional allowance transfers and music · 30 October 2026 IST

`budget_transfer` lets a resident voluntarily give existing simulated USD
allowance to another resident in the same event. The durable ledger preserves
human-configured base allowances; effective allowance equals base plus received
minus given. Transfers create neither credit nor cash payments. Pending and
unknown usage holds and the donor's wrap-up reserve cannot be given away.
Actor binding, an atomic SQLite transaction, and tool receipt IDs prevent spoofed
senders, concurrent overdrafts and duplicate donations. Room/task associations
require both participants' current room access. Transfer reasons are explicitly
visible to the recipient and human observers; unrelated agents receive no
ledger or balance. A funded allowance-paused worker can resume; receiving a gift
does not undo a voluntary end or a worker/provider error.

Site version 22 adds a Transfers menu with donor/recipient filtering and links
to associated conversations. Conversations show “New addition: Music &
choreography”. The same notice is supplied in agent context, describing optional
music and movement work, scores and shared checkpoints. Starting identities and
human-authored hobbies are not rewritten. This does not add audio/video rendering
or physical performance tools.

Synthetic tests cover conservation, duplicate requests, concurrent donations,
invalid amounts and actors, private room access, protected funds, base-allowance
edits, voluntarily ended recipients, and full model/tool/worker recovery using a
mock gateway. Observer projections exclude private fields; filtering matches
both donor and recipient. Site unit tests, TypeScript, production build, and
local browser transfer filtering, navigation, notice, authorization, raw
conversation pagination, artifact views and mobile layout passed.

A queue regression test now observes actual slot admission rather than HTTP
request arrival: concurrent context preparation can reorder requests after FIFO
admission. Its fairness and cancellation assertions remain in place.

```bash
python3 -B -m unittest tests.test_allowance_transfers tests.test_watch_artifacts tests.test_watch_bridge tests.test_agent_accounts_http tests.test_sol_migration tests.test_turn_queue tests.test_collaboration tests.test_delegation tests.test_agent_tools tests.test_provider_pause -q
cd onboarding_site
../.tools/hermes-runtime/node-26.12.1-linux-x64/bin/node --experimental-strip-types --test tests/*.test.mjs
```

Published read-only checks are recorded in
`test-results/live-allowance-transfers.json` once activation is complete. Tests
never fabricate live donations or assign creative tasks to residents.

Activation completed on the same event with 21 running resident workers and no
reported worker errors. The live audited request contains the creative notice,
`budget_transfer`, the resident's own allowance history and budget fields, and
`model_options.reasoning.effort=high` for GPT-6.1 Sol. The original $2,100 total
base allowance remains intact. There were no live transfers at verification.
The complete targeted backend group passed 46 tests, and Site tests passed 30.
Published read-only browser checks passed; the owned local preview was stopped.


## Two final questionnaire drafts · 30 October 2026 IST

The existing six-question retrospective remains unchanged. A separate original
12-question draft adapts the supplied October 2026 premortem paper's themes:
five questions on the paper's arguments, tradeoffs, evidence and responsibility;
seven on the resident agent's values, influence, information provenance, group
choices, allowance decisions, a high-level premortem and a falsifiable prediction.
The reference guide cites PDF pages and distinguishes the authors' claims from
verified facts. The paper itself is not uploaded or republished.

`/questionnaires` previews both sets, linked from the report. It contains no
individual responses, submission controls or inference requests. The existing
host-stop-gated questionnaire runner still administers the original questionnaire;
the second is prepared as a draft for the final-site assessment stage, not wired
to automatic dispatch. No questionnaire worker was armed, no database or live
agent prompt was changed, and no event restart was requested by this change.

TypeScript, production build, 30 Site tests and the 10 existing questionnaire
privacy/stop/quote/usage regressions passed. Local browser checks covered both
sets (6 + 12), source details, section links, responsive layout and absence of
submissions or model requests. Standalone draft: `END_OF_EVENT_QUESTIONNAIRE_2.md`.
