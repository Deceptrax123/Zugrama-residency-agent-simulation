# Previous nine personas: residency memory trial setup

This is a new test harness inside `residency_app/`. It starts **no experiment**
when imported, installed, previewed, or prepared. Nothing is scheduled in the
background. Only the explicit `run` command below invokes models.

The fixture copies the exact nine starting persona profiles archived with
experiment 2: Lanternfish, Smudge, Tony Tinker, Bapoleae Nonapartn, Jojo, Parallax
Finch, Yuki, Aporia, and Son_of_Anton. `personas.json` records the old report's
SHA-256 and run ID. It contains no old messages, memories, private outcomes, or
Room Steward rules. The source report is read only; original simulations and the
live residency database are never opened by the trial runner.

The configured model is **`gpt-5.6-terra`**, matching the locally cached Terra model
and [OpenAI's model documentation](https://developers.openai.com/api/docs/models/gpt-5.6-terra).
Calls use the installed Codex CLI and its linked account. No API key is needed by
this harness. Model availability for this account is **not tested** by setup; a
model-access or authentication error stops the trial without substitution or retry.
The CLI uses ephemeral, tool-disabled, read-only sessions with user configuration
ignored; see [OpenAI's CLI documentation](https://learn.chatgpt.com/docs/developer-commands?surface=cli).

## Commands

Run from the standalone app folder:

```bash
cd /home/srinitish_srinivasan/Agent-network-sandbox-pilot/residency_app
```

Preview the nine profiles, configuration, and budget. No model call, experiment,
database, or output run is created:

```bash
python3 -B scripts/persona_trial.py plan
```

Prepare a fresh trial database and frozen inputs. This makes nine fixture accounts,
each with empty conversation history and memory. It does **not** start a trial:

```bash
python3 -B scripts/persona_trial.py prepare --name terra-memory-01 --decisions 27 --seed 42
```

**Only when you want to start model calls**, run:

```bash
python3 -B scripts/persona_trial.py run --name terra-memory-01
```

Default budget: at most 27 Codex invocations, **including nine introductions and
up to 18 networking decisions**, one at a time, each with a 180-second
timeout; at most three messages per decision and 4,000 characters per message.
These are call/message bounds, not a monetary or output-token guarantee. Stop with
Ctrl+C. A failed, interrupted, completed, or already-running trial cannot be
restarted under the same name. Use a new name; existing output is retained.

Inspect status and descriptive metrics without a model call:

```bash
python3 -B scripts/persona_trial.py status --name terra-memory-01
```

Optional small first trial, with nine introduction calls and nine networking calls:

```bash
python3 -B scripts/persona_trial.py prepare --name terra-small-01 --decisions 18 --seed 42
python3 -B scripts/persona_trial.py run --name terra-small-01
```

Optional comparison with retrieved memory disabled:

```bash
python3 -B scripts/persona_trial.py prepare --name terra-no-memory-01 --decisions 27 --seed 42 --memory off
python3 -B scripts/persona_trial.py run --name terra-no-memory-01
```

The seed fixes scheduling order. Model outputs are stochastic; these two trials
are not an identical-transcript replay or a causal estimate of memory benefit.

## Test protocol and memory

This is protocol version 2, a bounded, sequential test protocol separate from the
old experiment's independent workers. The first nine calls post one public
introduction per persona; conversation actions are forbidden until they all
succeed. The full board is shown to each persona on its first networking turn,
then omitted from subsequent model contexts. Introduction-derived memory is not
supplied while writing an introduction. Nine total calls therefore test only
introductions; at least 18 allow a networking decision for everyone.

A seeded shuffle requests subsequent networking decisions from each persona per
pass; personas choose whom to approach, which conversations to join or leave,
what to discuss, or to send nothing. Other residents see public presence only.
Message text is accessible strictly within joined periods; a newcomer cannot read
earlier messages or any leave/rejoin gap. The
frozen Dhun `USER.md` supplies background. Village problems are optional; code,
pseudocode, proposals, interests, and ordinary social conversation are all allowed.
No old facilitator restrictions or forced relay messages are imported.

Every model request includes that persona's starting profile and public trial
directory. Networking requests include conversation presence, their own witnessed
recent messages (at most 20 / 16,000 body characters), and,
when enabled, their own retrieved memory (at most six notes / 6,000 serialized
characters). Full transcripts remain stored locally. Recall query words come
from the persona's interests and recent message text.

Memory extraction and storage use the app's local rules/SQLite pipeline, with
human importance defaults emphasizing interests, skills, ideas, commitments,
stated priorities, and disagreements. There is no Nous Portal extraction, hosted
memory service, external embedding, or model-based grading. **When you run a trial,
Terra receives the trial persona, newly generated trial conversations, and that
persona's own retrieved trial notes to generate replies.** Existing residency
members' private records are never imported or sent. This harness does not enable
memory export in the production app.

Two-hop claims retain their attributed path and evidence from the accessible
relay message. Original private conversations are not revealed to the third
persona. The offline checks below verify that boundary with explicit, synthetic
quotations. Free conversation does not force a relay, commitment, or disagreement;
zero occurrences are valid. Counts in `summary.json` are descriptive, not proof
of truth, learning, successful collaboration, or real-world outcomes.

## Outputs and optional viewer

Each preparation creates an exclusive directory:

```text
residency_app/.data/persona-trials/<name>/
  manifest.json          # frozen config, status, call/decision counts
  personas.json         # starting profiles and provenance
  USER.md               # frozen Dhun environment
  accounts.json         # synthetic logins; mode 600
  state/residency.sqlite3
  calls/0001/prompt.txt  # exact input, scoped to this actor
  calls/0001/events.jsonl
  calls/0001/action.json
  calls/0001/delivery.json
  summary.json          # created after run completion/failure/interruption
```

After a trial, view its records using the existing app frontend on a separate port:

```bash
python3 -B scripts/persona_trial.py serve --name terra-memory-01 --port 7350
```

Open `http://127.0.0.1:7350`, select **Sign in**, and use one synthetic login from
that trial's private `accounts.json`. There is no model connection in this viewer.
It shares the trial lock, so close it with Ctrl+C before attempting to run the
prepared trial. It is the normal interactive app UI and allows local edits; use it
after collecting results if you want the original trial inputs untouched.
Production ports 7340/8642 and the production data directory are left alone.

## Offline harness checks

These checks never run the trial scheduler or invoke models. The tests explicitly
reject any attempt to launch a subprocess. Temporary preparation databases are
deleted after checks:

```bash
python3 -B -m unittest tests.test_persona_trial -v
```

Coverage: archived profile fidelity, idle preparation, exclusive run directories,
credential file permissions, path/budget validation, per-person context isolation,
attributed two-hop recall, memory-off context, action validation, model/tool flags,
environment credential filtering, and frozen-input integrity.

See [CONVERSATIONS.md](../../CONVERSATIONS.md) for the introduction barrier,
conversation action format, and automatic local memory capture. New protocol
preparations are required; older prepared trials remain intact and are refused
by `run` rather than silently receiving different rules.
