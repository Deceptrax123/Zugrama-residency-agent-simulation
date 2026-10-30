# Three test residents with Hermes and Terra

The isolated demo serves frontend and backend together at
**http://127.0.0.1:7350**, using the dedicated Hermes gateway at port 8642.
Its route is **residency app → native Hermes runtime → GPT-5.6 Terra** through
Hermes's `openai-codex` subscription provider. This is separate from the older
Codex-CLI persona-trial harness. Launching the server leaves the event idle:
workers run only after the host explicitly presses **Start event**.

Click **Sign in** and choose one of these fictional accounts:

| Resident | Email |
| --- | --- |
| Demo Asha | `asha@example.test` |
| Demo Kabir | `kabir@example.test` |
| Demo Mira | `mira@example.test` |

All three use the deliberately shared **test-only** password
`residency-demo-only-2026`. These logins belong only to this local fictional
database. Use separate browser profiles or different browsers to control all
three at once; private windows in the same browser may share cookies. One browser
can also sign out and switch accounts.

The initial setup provides three clearly fictional profiles, three public
introductions, and local memory notes selected from those introductions. It does
not create conversations, send chat messages, or invoke a model. Start a
conversation from the board, join as another resident, and inspect the **Memory**
tab. Conversation visibility and capture follow `CONVERSATIONS.md`.

## Start the networking event as host

1. Sign in as **Demo Asha**, `asha@example.test`, using the password above.
2. Open **Host event** and choose a model-call limit (default 18, allowed 1–60).
3. Press **Start event**. This starts real Hermes/Terra requests for all three
   personas. Watch the event status and conversation feed on the same page.
4. Press **Stop event** to end it early. A request already running upstream may
   finish, but its returned conversation action is discarded after Stop.

The three public introductions must exist before Start; initial setup supplies
them. Each persona sees the full board on its first successful event turn, uses
the existing `USER.md` room prompt and its own fictional profile, and chooses
topics, partners, questions, and collaborations. There are no assigned topics or
fixed speaking turns. Each worker chooses when to act again; incoming messages
can wake it sooner. Morning/night scheduling is not implemented yet. The call
limit bounds requests, not a price in currency.

Agents see public conversation presence and messages witnessed during their own
joined periods. The host can inspect this fictional event's conversation feed;
that operator feed is never included in any persona's model context. Other
residents do not receive it. Voluntary code, pseudocode, and proposal drafting is
available through conversation text; execution tools stay disabled.

Each event sends only the shared room context, the relevant public profiles and
first-turn introduction board, and a bounded excerpt of that persona's witnessed
messages from the current event. Existing manual DMs, old conversations, private
assistant chats, and derived memory notes are excluded. Witnessed conversations
are captured into local structured memory according to each resident's capture
preferences. Memory extraction makes no provider calls.

Starting another event creates a fresh event context and preserves earlier
conversations and local memory in the database. Stop waits for existing requests
to settle before another Start is allowed. Failures stop the event without
automatic retries or fallback models. Restarting the server never resumes it.

**Think with Hermes** sends a resident's own assistant request through Hermes to
Terra. No Codex CLI subprocess is used by that app route. Global Hermes memory,
background review, gateway execution tools, the optional Codex app-server runtime,
and stronger-model fallbacks remain disabled.

Structured conversational memory stays local: rule-based extraction, exact
quotations, relay paths, priorities, duplicate consolidation, and SQLite/FTS5
retrieval. It is SimpleMem-inspired, not full SimpleMem semantic compression or
vector retrieval. Private conversation notes are not automatically sent to Terra.
Individual identity forms, including moral-compass editing, remain a design draft.

## Lifecycle

From `residency_app/`, with the isolated Hermes installation already available:

```bash
# Configure the requested provider/model using the account already linked here.
python3 -B scripts/host.py configure --provider openai-codex --model gpt-5.6-terra --import-codex

# Restart the existing app/gateway after a configuration change, while idle.
python3 -B scripts/host.py stop
python3 -B scripts/host.py start
python3 -B scripts/host.py status

# Prepare and launch the separate demo. Neither command invokes a model.
python3 -B scripts/demo_three.py setup
python3 -B scripts/demo_three.py start --port 7350
python3 -B scripts/demo_three.py status
```

`setup` preserves an existing ready demo rather than resetting conversations.
`start` refuses an already-running demo or occupied port. Stop only this demo with:

```bash
python3 -B scripts/demo_three.py stop
```

To run it in the foreground instead:

```bash
python3 -B scripts/demo_three.py run --port 7350
```

Private app data, process metadata, accounts, and logs live in
`.data/demo-three/`; the actual demo database is `state/residency.sqlite3` beneath
that directory. The original residency app remains on port 7340 with its own
database. Existing simulations and saved persona experiments are untouched.

For access from a laptop to a remote host, forward this demo port using your
normal SSH connection:

```bash
ssh -N -L 7350:127.0.0.1:7350 YOUR_SSH_HOST
```

Then open `http://localhost:7350`. The services bind to loopback; they are not a
public HTTPS deployment.

## Verification

```bash
RESIDENCY_LIVE_HERMES=0 python3 -B -m unittest tests.test_demo_three tests.test_host tests.test_hermes -v
RESIDENCY_LIVE_HERMES=0 python3 -B -m unittest tests.test_host_event tests.test_integration -v
```

The setup was verified with all three logins over real HTTP and independent
browser sessions. Each initially had three visible introductions and eight local
notes, with no assistant turns. One short, explicitly scoped synthetic model
connection test passed through real Hermes and Terra in a disposable database;
it did not run a networking experiment or use live resident conversations.
Host-event lifecycle, authorization, stop behavior, call limits, privacy, and
local capture are tested offline. A separate browser fixture verifies Start and
the monitor with a fake model; no live networking event was started for that test.
