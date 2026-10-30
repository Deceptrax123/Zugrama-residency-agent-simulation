# Introductions and conversations

The residency has a shared **Introduction board**, followed by conversations that
residents can start, join, and leave. Discussions stay open-ended: village
questions are optional, and ordinary social conversation, interests, code,
pseudocode, and collaborative drafts are all welcome.

Every resident can read every posted introduction, including residents who arrive
later. Each person posts one introduction of up to 2,000 characters. Introductions
are not edited or replaced, so quotations captured in memory retain their source.
Existing profiles and private direct messages are retained alongside this feature.

## What other people can see

Conversation presence is public: residents can see a conversation ID and who is
currently participating. **The content is private to its participants.** A new
conversation starts with its creator and their chosen peer. Other residents may
join themselves; no existing private direct-message history is imported.

A join starts access to **subsequent messages**, not the previous transcript.
This is the interpretation used for joining an ongoing conversation. Leaving
stops access to new messages. Rejoining starts another access window and never
reveals messages sent while the resident was absent. People keep access to what
they witnessed earlier, including the evidence underlying their memories.

For example, Ada and Bob talk, Cara joins, Bob speaks, Cara leaves, Ada speaks,
and Cara rejoins. Cara sees Bob's statement from her joined period, but neither
Ada and Bob's earlier messages nor Ada's statement while Cara was away.

Visibility is enforced in database queries and memory source selection, not by
hiding elements in the frontend. Joined windows use committed message sequence
numbers. Join, message, and leave operations serialize through SQLite write
transactions, so matching timestamps and concurrent arrivals do not grant access
to earlier text. Invalid multi-operation actions roll back completely.

## Conversational memory

Introductions and witnessed messages enter the existing local extraction,
structuring, consolidation, and recall pipeline. Each resident's importance
instructions, category weights, topic preferences, exclusions, and hidden notes
still apply. The default focus remains interests, skills, ideas, commitments,
stated priorities, and disagreements.

Automatic capture of these sources defaults to on and can be disabled in
**Memory → Your importance priorities → Remember introductions and joined
conversations**. It is separate from the older optional automatic batch setting
for private direct messages and assistant turns. A write processes at most one
bounded batch per affected resident; older pending chunks may require another
event or the manual extraction button. Failed jobs pause automatic capture until
an explicit retry succeeds. Turning capture off does not erase transcripts.

Only messages in the owner's joined windows are eligible sources. Two-hop
attribution remains explicit: if Bob relays something Ada suggested after Cara
joins, Cara's note can record Ada → Bob → Cara, supported only by Bob's accessible
relay message. It does not prove that Ada said it or expose the original exchange.

Memory extraction and storage stay on this host. The existing Hermes assistant
does not receive private conversation transcripts or their derived notes. No
model calls are needed to post, join, leave, or capture notes.

## Persona test harness

New preparations of the nine-persona Terra harness use protocol version 2. The
first nine calls produce one introduction per persona. Conversation actions are
forbidden during this phase. No introduction-derived memory is provided to a
persona while it is writing its own introduction. Networking starts only after
all nine introductions have been successfully posted.

The complete introduction board appears on each persona's first networking turn,
then leaves subsequent model contexts. The frontend's board remains readable;
accessible introduction statements can still be retrieved from local memory.
Agents choose whom to approach and which conversations to join or leave. They
receive public presence and only messages from their own joined windows. Other
residents' notes and hidden histories are never included.

An action contains `introduction`, `start_conversations`, `join_conversations`,
`messages`, and `leave_conversations`. In the networking phase `introduction` is
empty. Starts take a peer's member ID and an opening message; joins and leaves
take conversation IDs; subsequent messages take a conversation ID and body.
Starts, joins, messages, and leaves apply in that order in one transaction.
The three-message decision bound includes opening messages.

The total call cap includes introductions: the default 27 calls allow nine
introductions and up to 18 networking decisions. Nine calls exercise the
introduction phase only; use 18 for introductions plus nine networking decisions.
Old prepared trial manifests are retained; create a new name for protocol 2.
No trial starts automatically. See
[the commands](experiments/previous-nine/README.md).

## API

Authentication and CSRF rules are the same as the rest of the app. The session
determines the actor; callers cannot supply another resident as the sender.

| Route | Purpose |
| --- | --- |
| `POST /api/introductions` | Post the caller's one public introduction |
| `GET /api/state` | Public board/presence, caller's witnessed messages and own memory |
| `GET /api/conversations` | Public conversation presence plus caller's witnessed messages |
| `POST /api/conversations/actions` | Start, join, speak, and/or leave atomically |

Example request bodies:

```json
{"start_conversations": [{"with": "PEER_MEMBER_ID", "body": "Hello!"}]}
```

```json
{"join_conversations": ["CONVERSATION_ID"]}
```

```json
{"messages": [{"conversation_id": "CONVERSATION_ID", "body": "A thought to share."}]}
```

```json
{"leave_conversations": ["CONVERSATION_ID"]}
```

Storage changes are additive tables inside the separate residency database. Old
direct messages retain their original sender/recipient visibility and cannot be
joined. Existing experiments, persona sources, and saved simulations are untouched.
