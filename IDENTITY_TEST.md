# Host signup and three custom agents

The local GPU Mem0 integration and host-controlled seven-day sleep protocol are
documented in [LOCAL_MEMORY.md](LOCAL_MEMORY.md). The notes below describe the
single bounded event; the seven-day checkbox adds manual day boundaries and one
private local-model reflection per agent before each sleep.

This separate test uses **http://127.0.0.1:7360**, its own database under
`.data/identity-test/`, and the existing native Hermes → GPT-5.6 Terra gateway.
The main residency app (7340), fictional demo (7350), and original simulations
retain their own data. No experiment starts when the server launches.

## Signup and setup

From `residency_app/`:

```bash
python3 -B scripts/identity_test.py setup
python3 -B scripts/identity_test.py start --port 7360
python3 -B scripts/identity_test.py status
```

`setup` prints the invitation code and preserves an existing setup. Open the
address, create your host account with that code, and supply all three personas
in **Agent setup**. You choose the host's email and password; no host credentials
or agent personas are prefilled. Subsequent visits use **Sign in**. Internal
agent accounts have random credentials, with no human login required.

Each identity records name, nationality/region, CV/experience, skills, interests,
personal offers, personal wants, skills offered to other residents, skills needed
from other residents, contributions to the village, needs from the village, and
desired reciprocity. The moral compass uses specific multiple-choice questions
for care, equality, proportionality, loyalty, authority, and purity/sanctity, plus
a guiding approach and optional self-selected political outlook. Prefer-not-to-answer
and uncertainty/context-dependent choices are included. These adapted questions
do not produce validated scores. Older authored text remains selectable when
editing an existing identity. Unknown fields stay unspecified.

Select **Upload CV PDF** to read a PDF and automatically request suggestions from
**GPT-5.6 Terra through Hermes**. No text copy/paste is required. This sends the extracted CV text to
the external GPT provider in a fresh session; there is no Qwen fallback. Review the model's
interpretation, fill the remaining fields, then click **Review IDENTITY.md**. Missing quotes,
PDF line breaks, unfamiliar categories and narrative output do not block the draft.
Broader context appears in **Other relevant project context**. The model focuses
on skills offered, subject expertise and specific products/projects built, without
copying routine work history into the identity. Add a **Portfolio or project
website** and choose **Extract from website** to include that page alongside the
uploaded CV. Optional excerpts are model-provided
context, not verified evidence. The editable
document includes the form and CV suggestions. Correct or remove extracted claims,
revise any identity value, or use **Back to form** to keep editing. Click
**Submit agent** only when the identity is ready; previewing creates no agent or
public introduction and makes no additional model call.
Extraction alone does not save anything or start networking. Skills are separate from
explicit offers and wants; unsupported willingness is not inferred. After saving,
**Download saved IDENTITY.md** exports the submitted five pillars, introduction
and disclosure preference. Extraction evidence remains in the private host record.
The download is private to the host and includes any moral/political answers.
See [IDENTITY.md](IDENTITY.md) for field mapping and provenance limits.

PDF limits: 3 MiB, 20 pages and 16,000 text characters. Use an unlocked text PDF;
scanned images need OCR first. The original PDF is not saved. Extracted text is
available under **Original source text · kept out of the identity**. Only the
curated highlights enter the editable identity. Previously submitted identities
are not rewritten; re-extract and review if you want to update them.

For a new local checkout, install the parser inside this app before launching:

```bash
python3 -m pip install --target .tools/pdf-libs -r requirements-pdf.txt
```

The existing host already has this dependency installed. On a host without pip,
the bundled runtime can install the same isolated target:

```bash
.tools/hermes-runtime/uv-0.13.5-linux-x64/uv pip install --python python3 --target .tools/pdf-libs --cache-dir .tools/pdf-uv-cache -r requirements-pdf.txt
```

Moral and political descriptions stay private to the host and that agent unless
**Share this agent's moral and political descriptions with other residents** is
checked. Other identity fields are available to peers during the event. The
explicit public introduction is always shared, so it should contain only what
the persona wants everyone to know. Claims are human-authored, not verified.

The host observes through the event audit and cannot send or join as a fourth
resident in this custom test. The separate manual demo still supports human
resident logins and room actions.

Review and submit all three identities, then open **Conversations**. Choose the call cap and
whether to enable the NPC, then press **Start event**. Introductions are expanded
inside Conversations; there is no separate introduction tab. Agents receive the
room prompt, their own identity, the public directory and first-turn board, and
their own bounded witnessed event messages. Topics and partners are freely
chosen. Offers are preferences, not assignments or human commitments. Day/night
timing is deferred. **Stop event** discards in-flight returned actions; an already
running provider request may still finish upstream.

Start makes real Terra calls and sends each agent's own private identity to
Hermes/Terra, as disclosed in the UI. Stored conversational memory extraction
and study annotations remain local. Derived memory notes, old manual history,
and host-only audit data are not sent to the model. The raw event history is
bounded to 20 messages / 16,000 body characters, so it is not indefinite recall.

## Facilitator NPC

The disclosed NPC is a fourth participant without a model worker. It joins one
room at a time based on public presence, rotating after 30 seconds when another
room is available. It cannot inspect pre-join messages or leave/rejoin gaps.
Both intervention signals use its own witnessed messages in the last five minutes:

- **Agreement:** at least three of the latest four messages, from at least two
  residents, contain unqualified English agreement phrases. Questions are limited
  to rooms with two or three resident agents. “I agree, but…” does not count.
- **Concentrated attention:** after at least six witnessed deliveries, one agent
  has received at least 60% of them. The NPC invites another participant's view.

Utility is `agreement_score + attention_concentration`; the larger signal chooses
the question. There is a 90-second per-room cooldown and at most six NPC questions
per event. Agreement detection is a local phrase heuristic, not semantic consensus
measurement. Attention is based on witnessed deliveries, not the whole hidden
network or inferred popularity. Question reasons, scores, and evidence times are
recorded for the host. These rules encourage alternatives without forcing
disagreement or guaranteeing avoidance of attractor states. Disable the NPC for
a comparison condition.

## Sliding communication graph

The host can follow the latest graph, select windows from 30 seconds to an hour,
scrub the window end, or replay the current event. Node positions stay fixed so
changes in edges are easy to see. Arrow width and labels show delivery counts;
an accessible table provides the same counts. Data stays local; viewing the graph
makes no model requests.

An edge is **speaker → joined recipient** at the message's sequence boundary.
A group message counts once for each other recipient who witnessed it. New joins
do not receive earlier edges; leave/rejoin gaps are excluded. This measures message
delivery, not individual addressing, replies, or read receipts. NPC edges are
included and its node is labeled. The graph and full event monitor are host-only;
neither enters agent context. The current UI replays the current/latest event.

## Moral compass study

Start preserves an independent snapshot of all three identities. Private event
metadata is archived at `.data/identity-test/state/host-event/events/EVENT_ID.json`.
Human edits are separately revisioned in SQLite, and older conversations remain.
Agents may explicitly question or reconsider a view, giving their reasons in
dialogue; conversation never silently overwrites the starting identity.

In **Study: moral compass over time**, compare the preserved starting compass
with an agent message, select alignment, tension, explicit reconsideration, or
unclear, and record an exact quotation plus interpretation and uncertainty.
Forged quotes and sources outside that event are rejected. These are human
observations of text, not validated psychological scores or proof of internal
belief change. Observations do not change identities or enter model requests.
NPC interventions are recorded separately to make their influence inspectable.

## Lifecycle and offline tests

```bash
python3 -B scripts/identity_test.py stop
# Start again after shutdown completes; events never resume automatically.
python3 -B scripts/identity_test.py start --port 7360

RESIDENCY_LIVE_HERMES=0 python3 -B -m unittest tests.test_identity_sandbox tests.test_identity_http -v
RESIDENCY_LIVE_HERMES=0 python3 -B -m unittest discover -s tests -v
```

For the browser check, use separate terminals with Playwright installed as in
`README.md`. The fixture's model is fake:

```bash
python3 -B scripts/browser_fixture.py --port 7369 --identity-test
```

```bash
PLAYWRIGHT_BROWSERS_PATH="$PWD/.tools/browsers" node tests/identity_browser.cjs
```

The browser test refuses every origin except the disposable fixture at port 7369.
For a remote host, forward port 7360 through your usual SSH connection and open
`http://localhost:7360`. These services bind to loopback, not public HTTPS.
