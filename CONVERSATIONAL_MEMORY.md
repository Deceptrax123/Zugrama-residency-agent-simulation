# Conversational memory for the residency

Each resident has a private memory store beside their conversations. The shared
Dhun environment and the identity design remain separate: conversation notes do
not silently rewrite a person's identity, moral compass, or political standing.
There is no requirement to discuss village problems or produce projects.

The design follows the extraction, synthesis, and retrieval stages described by
[SimpleMem](https://arxiv.org/abs/2601.02553) and its
[official implementation](https://github.com/aiming-lab/SimpleMem). This app does
not install the upstream SDK or claim its algorithm, semantic compression,
intent planning, embeddings, or benchmark performance. The working baseline is
local extractive rules plus SQLite/FTS5. The user chose to keep conversational
memory local. There is no external extraction or private-memory recall in Hermes.

## What is available now

Open **Memory** in the frontend. A resident can:

- Set importance priorities in their own words, preferred topics, excluded
  phrases, and category weights: facts, interests, skills, offers, requests,
  commitments, ideas, stated priorities, relationships, disagreements, and logistics.
- Extract a bounded batch on demand, or opt into automatic local batches after
  their next contribution when enough unprocessed source chunks exist.
- Inspect selected statements, category, importance score/reason, attribution
  path, original quotations, source IDs, and timestamps.
- Search and rank notes, restrict recall to a person in the attribution path,
  pin a note, hide it, or manually select a quotation and write its statement.

The local extractor categorizes individual sentences using documented speech and
activity patterns. Scores reflect category weights, topic matches, priority-word
overlap, and explicit offers/requests/commitments. This is an attention score, not
a probability of truth or a psychological assessment. Natural-language priorities
are matched as words; complex instructions are not semantically interpreted.
Raw wording is retained with the speaker's name instead of guessing referents.
Long passages and code remain available for manual quotation selection.

The residency default gives **High (2)** weight to interests, skills, ideas,
commitments, stated priorities, and disagreements; other categories stay at
**Normal (1)**. Each resident can change these weights and the accompanying
instruction. Previously saved settings keep their existing values, with the new
priorities category added at High. Explicit phrases such as “my priority” or
“most important to me” identify stated priorities; hidden motives are not inferred.

## Sources and two-hop claims

Sources include only the owner's sent/received messages, their completed private
assistant turns, public problem threads they authored or commented on, the public
introduction board, and conversation messages witnessed within their joined periods.
Excluded phrases remove matching source chunks from extraction. Unrelated private
conversations and other residents' assistant histories are inaccessible.

For example:

1. Ada talks privately to Bob.
2. Bob tells Cara: “Ada suggested a rainwater prototype for the village.”
3. Cara's note records the quotation from **Bob → Cara**, with the attributed path
   **Ada → Bob → Cara**, and the type **relayed claim**.

Cara does not gain access to Ada and Bob's conversation. The original suggestion
remains an unverified attribution. Reported origins require an explicit speech
phrase in the accessible quotation, such as “Ada suggested” or “according to Ada.”
The local extractor recognizes known directory names. Manually selected notes can
also name an unresolved origin; duplicate names remain unresolved rather than
arbitrarily linking a resident. This is two-hop attribution, not an unrestricted
social-graph traversal or proof that Ada actually made the statement.

Each memory unit has an owner, statement, category, source type, optional subject,
origin name, attribution path, keywords, importance/reason, optional event time,
wording variants, pin/hidden flags, and creation/update timestamps. Evidence stores
the exact source key, quotation, speaker, and occurrence timestamp. Assistant
output is labeled **assistant draft**, and a resident's own words **self report**.
Conversation timestamps are always retained. Local extraction leaves inferred
event times empty rather than guessing what “tomorrow” means.

## Synthesis and recall

Exact duplicate statements with the same attributed path consolidate their
evidence. Different statements, including contradictory ones, remain separate.
The storage layer also supports an extractor proposing a merge into a retrieved
note: it must have the same owner, source type, path, category, and subject. All
wording and evidence are retained. The local extractor only deduplicates exact
statements; it does not perform abstract semantic synthesis.

FTS5 BM25 matches, word overlap, optional person filters, human category weights,
preferred topics, pin status, and recency rank recall. Search ranks available notes
rather than requiring every result to contain the query. Recall defaults to at
most six units and a 6,000-character serialized budget. There is no vector search
or query-planning model. Turning recall off returns no retrieved notes while
leaving stored notes inspectable. A hidden duplicate cannot reappear through a
later extraction. Hidden notes can be restored with the owner-only note PATCH API.
Exclusions apply to extraction and recall, including evidence, but do not erase
existing transcripts or stored notes. Existing notes stay inspectable until hidden.

## Costs and failure handling

The current path uses Python's standard library and the app's SQLite database.
It makes **zero model, embedding, or hosted memory calls**. It runs without Hermes
credentials. Existing assistant chat behavior is unchanged; local memory and
private DMs are not automatically added to its provider payload. The resident can
choose what to copy into a chat themselves.

A batch contains at most 12 source chunks / 12,000 source characters, selecting up
to eight notes. Long sources use 4,000-character chunks with a 160-character overlap.
Not every sentence is retained: selected notes reflect the current priorities;
raw transcripts remain available for manual selection. Successfully examined
chunks are marked processed even if no note is selected. Policy changes affect
future batches and current recall; they do not automatically re-extract old chunks.

Jobs serialize per resident. Validation checks source access, exact quotation
matches, speaker consistency, explicit relay attribution, and unit structure
before committing a batch. Failed batches leave sources unprocessed and pause
automatic extraction until an explicit retry succeeds. No retry loop or stronger
model fallback exists. Interrupted jobs are marked failed at startup.

Public introductions and witnessed joined-conversation messages also support
automatic local capture, on by default under the separate `capture_conversations`
policy switch. This does not enable automatic legacy DM/chat batches. A join
does not backfill earlier conversation text; leave/rejoin gaps stay inaccessible
to both memory source selection and raw transcript views. See
[CONVERSATIONS.md](CONVERSATIONS.md) for the sequence-window rules and persona
introduction phase. Memory extraction still makes zero model calls.

The user explicitly selected **Keep memory local for now**. Memory extraction and
retrieval have no provider integration, opt-in prompt, or outgoing memory payload.
Existing direct Hermes chat continues separately with its existing context.

## API

All routes require the existing authenticated session; writes require its CSRF
token. The server derives the owner from the session, never the request body.

| Route | Purpose |
| --- | --- |
| `GET /api/memory?q=...&peer=...` | Own notes, priorities, ranked recall, batch status |
| `GET /api/memory/sources` | Own accessible source chunks for manual selection |
| `PATCH /api/memory/policy` | Own importance priorities and local switches |
| `POST /api/memory/extract` | One local batch; no external request |
| `POST /api/memory/notes` | Human-selected statement with exact source quotation |
| `PATCH /api/memory/notes/{id}` | Owner-only boolean `pinned` / `hidden` controls |

The existing app's private SQLite database gains additive memory tables and an
FTS5 index. Existing records are retained. All implementation, schema, frontend,
tests, and documentation changes stay inside `residency_app/`.
