"""SimpleMem-inspired local memory: extract, synthesize, retrieve, preserve evidence.

Uses SQLite/FTS5 and local extractive rules, not the upstream SDK or a hosted
memory account. No source data is sent to Hermes. Attribution is a claim.
"""
from datetime import datetime, timezone
import hashlib
import json
import math
import re
import sqlite3
import time
import uuid

from .store import AppError, text

CATEGORIES = ("facts", "interests", "skills", "offers", "requests", "commitments",
              "ideas", "priorities", "relationships", "disagreements", "logistics")
DEFAULT_FOCUS = frozenset(("interests", "skills", "ideas", "commitments", "priorities", "disagreements"))
BATCH_SOURCES = 12
BATCH_CHARACTERS = 12000
MAX_UNITS = 8
AUTOMATIC_BATCH_KINDS = frozenset(('direct_message', 'self_report', 'assistant_draft', 'public_thread'))


def create_schema(db):
    db.executescript("""
        CREATE TABLE IF NOT EXISTS memory_policies(
            owner_id TEXT PRIMARY KEY REFERENCES members(id), data TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS memory_units(
            id TEXT PRIMARY KEY, owner_id TEXT NOT NULL REFERENCES members(id),
            summary TEXT NOT NULL, category TEXT NOT NULL, kind TEXT NOT NULL,
            subject_id TEXT, origin_name TEXT NOT NULL, path TEXT NOT NULL,
            keywords TEXT NOT NULL, variants TEXT NOT NULL, importance REAL NOT NULL,
            reason TEXT NOT NULL, event_time TEXT, signature TEXT NOT NULL,
            pinned INTEGER NOT NULL DEFAULT 0, hidden INTEGER NOT NULL DEFAULT 0,
            created_at REAL NOT NULL, updated_at REAL NOT NULL,
            UNIQUE(owner_id, signature));
        CREATE TABLE IF NOT EXISTS memory_evidence(
            memory_id TEXT NOT NULL REFERENCES memory_units(id),
            source_key TEXT NOT NULL, quote TEXT NOT NULL, speaker_id TEXT NOT NULL,
            occurred_at REAL NOT NULL, PRIMARY KEY(memory_id,source_key,quote));
        CREATE TABLE IF NOT EXISTS memory_processed(
            owner_id TEXT NOT NULL REFERENCES members(id), source_key TEXT NOT NULL,
            job_id TEXT NOT NULL, PRIMARY KEY(owner_id,source_key));
        CREATE TABLE IF NOT EXISTS memory_jobs(
            id TEXT PRIMARY KEY, owner_id TEXT NOT NULL REFERENCES members(id),
            status TEXT NOT NULL, source_count INTEGER NOT NULL, unit_count INTEGER NOT NULL DEFAULT 0,
            error TEXT, created_at REAL NOT NULL, finished_at REAL);
        CREATE UNIQUE INDEX IF NOT EXISTS one_memory_job
            ON memory_jobs(owner_id) WHERE status='running';
        CREATE INDEX IF NOT EXISTS memory_owner ON memory_units(owner_id,hidden);
        CREATE VIRTUAL TABLE IF NOT EXISTS memory_search USING fts5(
            memory_id UNINDEXED, owner_id UNINDEXED, content, tokenize='unicode61');
    """)
    db.execute("UPDATE memory_jobs SET status='failed',error='App restarted during extraction; no automatic retry.',finished_at=? WHERE status='running'", (time.time(),))


def default_policy():
    return {"instructions": "Prioritize people's interests and skills, ideas, commitments, stated priorities, and disagreements.",
            "topics": [], "exclude_terms": [],
            "weights": {category: 2 if category in DEFAULT_FOCUS else 1 for category in CATEGORIES}, "minimum_importance": 0.25,
            "auto_extract": False, "auto_after": 6, "recall_enabled": True, "capture_conversations": True, "network_context": False}


def terms(value):
    return set(re.findall(r"[^\W_]+", value.casefold(), re.UNICODE))


def excluded(value, policy):
    lowered = value.casefold()
    return any(term.casefold() in lowered for term in policy["exclude_terms"])


class ConversationMemory:
    def __init__(self, store):
        self.store = store

    def policy(self, owner):
        with self.store.db() as db:
            row = db.execute("SELECT data FROM memory_policies WHERE owner_id=?", (owner,)).fetchone()
        policy = default_policy()
        if row:
            saved = json.loads(row[0])
            # Add new categories without changing any resident's saved choices.
            weights = {**policy["weights"], **saved.get("weights", {})}
            policy.update(saved)
            policy["weights"] = weights
        return policy

    def set_policy(self, owner, payload):
        policy = self.policy(owner)
        for key in ("instructions", "topics", "exclude_terms", "weights", "minimum_importance",
                    "auto_extract", "auto_after", "recall_enabled", "capture_conversations", "network_context"):
            if key in payload:
                policy[key] = payload[key]
        policy["instructions"] = text(policy["instructions"], "Memory priorities", 2000, False)
        if not isinstance(policy['topics'], list) or len(policy['topics']) > 20:
            raise AppError('topics must be a list of at most 20 phrases')
        policy['topics'] = list(dict.fromkeys(text(v, 'topics', 80) for v in policy['topics']))
        if not isinstance(policy['exclude_terms'], list):
            raise AppError('Memory exclusions must be a list of text')
        exclusions = [clean for v in policy['exclude_terms'] if (clean := text(v, 'Excluded phrase', 100000, False))]
        if sum(map(len, exclusions)) > 100000:
            raise AppError('Keep memory exclusions within 100,000 characters')
        policy['exclude_terms'] = list(dict.fromkeys(exclusions))
        if not isinstance(policy["weights"], dict) or set(policy["weights"]) != set(CATEGORIES):
            raise AppError("Provide a weight for each memory category")
        if any(type(v) is not int or not 0 <= v <= 3 for v in policy["weights"].values()):
            raise AppError("Category weights must be integers from 0 (ignore) to 3 (highest)")
        if any(type(policy[k]) is not bool for k in ("auto_extract", "recall_enabled", "capture_conversations", "network_context")):
            raise AppError("Memory switches must be booleans")
        if type(policy["auto_after"]) is not int or not 1 <= policy["auto_after"] <= 24:
            raise AppError("Automatic extraction threshold must be 1–24 source chunks")
        minimum = policy["minimum_importance"]
        if type(minimum) not in (int, float) or not math.isfinite(minimum) or not 0 <= minimum <= 1:
            raise AppError("Minimum importance must be between 0 and 1")
        with self.store.db() as db:
            db.execute("INSERT INTO memory_policies VALUES(?,?) ON CONFLICT(owner_id) DO UPDATE SET data=excluded.data",
                       (owner, json.dumps(policy)))
        return policy

    def sources(self, owner, pending_only=True):
        # Every SQL branch is scoped to something this owner sent, received, or joined.
        with self.store.db() as db:
            messages = [dict(r) for r in db.execute("SELECT * FROM messages WHERE sender_id=? OR recipient_id=?", (owner, owner))]
            turns = [dict(r) for r in db.execute("SELECT * FROM assistant_turns WHERE member_id=? AND status='completed'", (owner,))]
            problems = [dict(r) for r in db.execute("SELECT * FROM problems WHERE member_id=? OR id IN (SELECT problem_id FROM comments WHERE member_id=?)", (owner, owner))]
            comments = [dict(r) for r in db.execute("SELECT * FROM comments WHERE problem_id IN (SELECT id FROM problems WHERE member_id=? UNION SELECT problem_id FROM comments WHERE member_id=?)", (owner, owner))]
            processed = {r[0] for r in db.execute("SELECT source_key FROM memory_processed WHERE owner_id=?", (owner,))} if pending_only else set()
        events = []
        for row in messages:
            events.append(("message:" + row["id"], row["sender_id"], row["body"], row["created_at"], "direct_message"))
        for row in turns:
            events.extend([("turn:" + row["id"] + ":user", owner, row["prompt"], row["created_at"], "self_report"),
                           ("turn:" + row["id"] + ":assistant", "hermes", row["reply"], row["created_at"], "assistant_draft")])
        for row in problems:
            events.append(("problem:" + row["id"], row["member_id"], row["title"] + "\n" + row["body"], row["created_at"], "public_thread"))
        for row in comments:
            events.append(("comment:" + row["id"], row["member_id"], row["body"], row["created_at"], "public_thread"))
        for row in self.store.introductions():
            events.append(("introduction:" + row['id'], row['member_id'], row['body'], row['created_at'], 'introduction'))
        for row in self.store.conversation_state(owner)['conversation_messages']:
            events.append(('conversation:' + row['id'], row['sender_id'], row['body'], row['created_at'], 'joined_conversation'))
        policy = self.policy(owner)
        result = []
        for key, speaker, body, at, kind in sorted(events, key=lambda row: (row[3], row[0])):
            # Overlapping chunks avoid silently dropping the end of long drafts/code.
            for offset in range(0, len(body), 3840):
                chunk_key = f"{key}:{offset}"
                chunk = body[offset:offset + 4000]
                if chunk_key in processed or excluded(chunk, policy):
                    continue
                result.append({"key": chunk_key, "speaker_id": speaker, "body": chunk,
                               "occurred_at": at, "kind": kind,
                               "timestamp": datetime.fromtimestamp(at, timezone.utc).isoformat()})
        return result

    def batch(self, owner, source_kinds=None):
        result, size = [], 0
        for source in self.sources(owner):
            if source_kinds is not None and source['kind'] not in source_kinds:
                continue
            if len(result) >= BATCH_SOURCES or size + len(source["body"]) > BATCH_CHARACTERS:
                break
            result.append(source)
            size += len(source["body"])
        return result

    def should_process(self, owner):
        policy = self.policy(owner)
        if not policy["auto_extract"] or sum(s['kind'] in AUTOMATIC_BATCH_KINDS for s in self.sources(owner)) < policy["auto_after"]:
            return False
        with self.store.db() as db:
            last = db.execute("SELECT status FROM memory_jobs WHERE owner_id=? ORDER BY created_at DESC LIMIT 1", (owner,)).fetchone()
        # A failure pauses automatic retries until the human explicitly tries again.
        return not last or last[0] == "completed"

    def capture_conversations(self, owner):
        if not self.policy(owner)['capture_conversations']:
            return
        with self.store.db() as db:
            latest = db.execute('SELECT status FROM memory_jobs WHERE owner_id=? ORDER BY created_at DESC LIMIT 1', (owner,)).fetchone()
        if latest and latest[0] in ('failed', 'running'):
            return
        return self.process(owner, local_extract, source_kinds={'introduction', 'joined_conversation'})

    def process(self, owner, extractor, source_kinds=None):
        sources = self.batch(owner, source_kinds)
        if not sources:
            return {"status": "idle", "processed_sources": 0, "stored_units": 0, "remaining": 0}
        job_id, now = uuid.uuid4().hex, time.time()
        try:
            with self.store.db() as db:
                db.execute("BEGIN IMMEDIATE")
                processed = {r[0] for r in db.execute("SELECT source_key FROM memory_processed WHERE owner_id=?", (owner,))}
                sources = [source for source in sources if source["key"] not in processed]
                if not sources:
                    return {"status": "idle", "processed_sources": 0, "stored_units": 0, "remaining": 0}
                db.execute("INSERT INTO memory_jobs(id,owner_id,status,source_count,created_at) VALUES(?,?,'running',?,?)",
                           (job_id, owner, len(sources), now))
        except sqlite3.IntegrityError:
            raise AppError("A memory extraction is already running for you", 409) from None
        try:
            with self.store.db() as db:
                people = [dict(r) for r in db.execute("SELECT id,name FROM members")]
            policy = self.policy(owner)
            # Prior related notes are a synthesis hint, never a source of new evidence.
            prior = self.recall(owner, " ".join(s["body"] for s in sources), limit=5, budget=4500)
            units = extractor(owner, job_id, {"owner_id": owner, "people": people,
                "priorities": policy, "sources": sources, "existing_memories": prior})
            if not isinstance(units, list) or len(units) > MAX_UNITS:
                raise AppError("Memory extraction returned an invalid unit list", 502)
            by_key = {source["key"]: source for source in sources}
            validated = [self.validate(unit, owner, by_key, people) for unit in units]
            policy = self.policy(owner)
            count = 0
            with self.store.db() as db:
                for unit in validated:
                    if (policy["weights"][unit["category"]] == 0 or excluded(json.dumps(unit), policy)
                            or unit["importance"] < policy["minimum_importance"]):
                        continue
                    if self.save_unit(db, owner, unit, {m["id"] for m in prior}):
                        count += 1
                db.executemany("INSERT OR IGNORE INTO memory_processed VALUES(?,?,?)",
                               [(owner, source["key"], job_id) for source in sources])
                db.execute("UPDATE memory_jobs SET status='completed',unit_count=?,finished_at=? WHERE id=?", (count, time.time(), job_id))
            return {"status": "completed", "processed_sources": len(sources), "stored_units": count,
                    "remaining": len(self.sources(owner)), "job_id": job_id}
        except Exception as exc:
            error = str(exc) if isinstance(exc, AppError) else "Memory extraction failed; no automatic retry was made."
            with self.store.db() as db:
                db.execute("UPDATE memory_jobs SET status='failed',error=?,finished_at=? WHERE id=?", (error, time.time(), job_id))
            if isinstance(exc, AppError):
                raise
            raise AppError(error, 502) from None

    def validate(self, unit, owner, sources, people):
        if not isinstance(unit, dict):
            raise AppError("Invalid memory unit", 502)
        summary = text(unit.get("summary"), "Memory summary", 800)
        category = unit.get("category")
        if category not in CATEGORIES:
            raise AppError("Invalid memory category", 502)
        importance = unit.get("importance")
        if type(importance) not in (float, int) or not math.isfinite(importance) or not 0 <= importance <= 1:
            raise AppError("Invalid memory importance", 502)
        evidence = unit.get("evidence")
        if not isinstance(evidence, list) or not 1 <= len(evidence) <= 3:
            raise AppError("Each memory needs 1–3 source quotations", 502)
        quotes = []
        for item in evidence:
            if not isinstance(item, dict) or not isinstance(item.get("source_key"), str) or item["source_key"] not in sources:
                raise AppError("Memory cited an unavailable conversation", 502)
            source = sources[item["source_key"]]
            quote = text(item.get("quote"), "Evidence quotation", 1200)
            if quote not in source["body"]:
                raise AppError("Memory quotation does not match its source", 502)
            quotes.append({"source_key": source["key"], "quote": quote,
                           "speaker_id": source["speaker_id"], "occurred_at": source["occurred_at"]})
        speaker = quotes[0]["speaker_id"]
        if any(q["speaker_id"] != speaker for q in quotes):
            raise AppError("Keep statements from different speakers in separate memory units", 502)
        origin = text(unit.get("reported_origin", ""), "Reported origin", 80, False)
        names = {person["id"]: person["name"] for person in people}
        subject = unit.get("subject_id") or None
        if subject is not None and (not isinstance(subject, str) or subject not in names):
            raise AppError("Unknown memory subject", 502)
        kind = "assistant_draft" if speaker == "hermes" else "self_report" if speaker == owner else "direct_statement"
        path = [speaker] if speaker == owner else [speaker, owner]
        if origin:
            if speaker == "hermes":
                raise AppError("Assistant-generated text cannot establish a human attribution chain", 502)
            # Name + explicit speech attribution must occur in the accessible quotation.
            pattern = r"(?<!\w)" + re.escape(origin) + r"\s+(?:(?:has|had)\s+)?(?:said|says|told|mentioned|suggested|shared|recommended)\b"
            reverse = r"\baccording to\s+" + re.escape(origin) + r"\b"
            if not any(re.search(pattern, q["quote"], re.I | re.S) or re.search(reverse, q["quote"], re.I) for q in quotes):
                raise AppError("A relayed claim needs explicit attribution in the quoted message", 502)
            matching = [person["id"] for person in people if person["name"].casefold() == origin.casefold()]
            origin_id = matching[0] if len(matching) == 1 else "unresolved:" + origin
            if origin_id in (speaker, owner):
                raise AppError("Invalid relayed attribution chain", 502)
            kind, path = "relayed_claim", [origin_id, *path]
        keywords = unit.get("keywords", [])
        if not isinstance(keywords, list) or len(keywords) > 12:
            raise AppError("Invalid memory keywords", 502)
        keywords = [text(k, "Keyword", 60) for k in keywords]
        event_time = unit.get("event_time") or None
        if event_time:
            try:
                parsed = datetime.fromisoformat(event_time)
                if parsed.tzinfo is None:
                    raise ValueError()
            except (ValueError, TypeError):
                raise AppError("Memory event time requires an absolute timestamp and timezone", 502) from None
        merge_with = unit.get("merge_with")
        if merge_with is not None and not isinstance(merge_with, str):
            raise AppError("Invalid synthesis target", 502)
        return {"summary": summary, "category": category, "kind": kind,
                "subject_id": subject, "origin_name": origin, "path": path,
                "keywords": keywords, "importance": float(importance),
                "reason": text(unit.get("reason", ""), "Importance reason", 600, False),
                "event_time": event_time, "evidence": quotes, "merge_with": merge_with}

    def save_unit(self, db, owner, unit, allowed_merges):
        signature = hashlib.sha256(json.dumps([" ".join(unit["summary"].casefold().split()), unit["kind"],
            unit["path"], unit["subject_id"]], sort_keys=True).encode()).hexdigest()
        existing = db.execute("SELECT * FROM memory_units WHERE owner_id=? AND signature=?", (owner, signature)).fetchone()
        if not existing and unit["merge_with"] in allowed_merges:
            candidate = db.execute("SELECT * FROM memory_units WHERE owner_id=? AND id=? AND hidden=0", (owner, unit["merge_with"])).fetchone()
            if (candidate and candidate["kind"] == unit["kind"] and candidate["path"] == json.dumps(unit["path"])
                    and candidate["category"] == unit["category"] and candidate["subject_id"] == unit["subject_id"]):
                existing = candidate
        now = time.time()
        if existing:
            if existing["hidden"]:
                return  # A duplicate must not resurrect a hidden note.
            memory_id = existing["id"]
            variants = list(dict.fromkeys([*json.loads(existing["variants"]), unit["summary"]]))
            # Keep each variation rather than silently replacing a conflicting claim.
            db.execute("UPDATE memory_units SET variants=?,updated_at=? WHERE id=?", (json.dumps(variants), now, memory_id))
        else:
            memory_id = uuid.uuid4().hex
            db.execute("""INSERT INTO memory_units(id,owner_id,summary,category,kind,subject_id,origin_name,path,
                keywords,variants,importance,reason,event_time,signature,created_at,updated_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", (memory_id, owner, unit["summary"], unit["category"],
                unit["kind"], unit["subject_id"], unit["origin_name"], json.dumps(unit["path"]), json.dumps(unit["keywords"]),
                json.dumps([unit["summary"]]), unit["importance"], unit["reason"], unit["event_time"], signature, now, now))
        for quote in unit["evidence"]:
            db.execute("INSERT OR IGNORE INTO memory_evidence VALUES(?,?,?,?,?)", (memory_id, quote["source_key"], quote["quote"], quote["speaker_id"], quote["occurred_at"]))
        row = db.execute("SELECT summary,keywords,variants FROM memory_units WHERE id=?", (memory_id,)).fetchone()
        db.execute("DELETE FROM memory_search WHERE memory_id=?", (memory_id,))
        db.execute("INSERT INTO memory_search VALUES(?,?,?)", (memory_id, owner, " ".join(row)))
        return memory_id

    def units(self, owner, include_hidden=False):
        with self.store.db() as db:
            rows = [dict(r) for r in db.execute("SELECT * FROM memory_units WHERE owner_id=? ORDER BY updated_at DESC", (owner,))]
            evidence = {}
            for row in db.execute("SELECT e.* FROM memory_evidence e JOIN memory_units m ON m.id=e.memory_id WHERE m.owner_id=? ORDER BY e.occurred_at", (owner,)):
                evidence.setdefault(row["memory_id"], []).append(dict(row))
        result = []
        for row in rows:
            if row["hidden"] and not include_hidden:
                continue
            for key in ("path", "keywords", "variants"):
                row[key] = json.loads(row[key])
            row["evidence"] = evidence.get(row["id"], [])
            result.append(row)
        return result

    def recall(self, owner, query, limit=6, budget=6000, peer_id=None):
        policy = self.policy(owner)
        if not policy["recall_enabled"]:
            return []
        query_terms = terms(query)
        lexical = {}
        if query_terms:
            expression = " OR ".join('"' + token.replace('"', '""') + '"' for token in sorted(query_terms)[:24])
            with self.store.db() as db:
                for rank, row in enumerate(db.execute("SELECT memory_id FROM memory_search WHERE memory_search MATCH ? AND owner_id=? ORDER BY bm25(memory_search) LIMIT 60", (expression, owner))):
                    lexical[row[0]] = 1 / (rank + 1)
        ranked = []
        for row in self.units(owner):
            content = " ".join([row["summary"], *row["keywords"], *row["variants"]])
            if excluded(content + json.dumps(row["evidence"]), policy) or policy["weights"][row["category"]] == 0:
                continue
            if peer_id and peer_id not in row["path"] and row["subject_id"] != peer_id:
                continue
            relevance = len(query_terms & terms(content)) / max(1, len(query_terms))
            topic = sum(bool(terms(value) & terms(content)) for value in policy["topics"])
            age = max(0, time.time() - row["updated_at"])
            score = (10 * row["pinned"] + 3 * relevance + lexical.get(row["id"], 0)
                     + policy["weights"][row["category"]] * row["importance"] + min(topic, 3)
                     + .1 / (1 + age / 86400))
            ranked.append((score, row))
        result, size = [], 0
        for _, row in sorted(ranked, key=lambda pair: pair[0], reverse=True):
            compact = {key: row[key] for key in ("id", "summary", "category", "kind", "subject_id", "origin_name", "path", "importance", "reason", "event_time", "pinned")}
            compact["variants"] = row["variants"][-3:]
            compact["evidence"] = row["evidence"][-2:]
            length = len(json.dumps(compact, ensure_ascii=False))
            if size + length <= budget:
                result.append(compact)
                size += length
            if len(result) >= limit:
                break
        return result

    def update_unit(self, owner, memory_id, payload):
        if not payload or set(payload) - {"pinned", "hidden"} or any(type(v) is not bool for v in payload.values()):
            raise AppError("Memory controls accept pinned and hidden booleans only")
        with self.store.db() as db:
            if not db.execute("SELECT 1 FROM memory_units WHERE id=? AND owner_id=?", (memory_id, owner)).fetchone():
                raise AppError("Memory not found", 404)
            for key, value in payload.items():
                db.execute(f"UPDATE memory_units SET {key}=? WHERE id=? AND owner_id=?", (int(value), memory_id, owner))

    def view(self, owner, query="", peer_id=None):
        with self.store.db() as db:
            row = db.execute("SELECT * FROM memory_jobs WHERE owner_id=? ORDER BY created_at DESC LIMIT 1", (owner,)).fetchone()
            calls = db.execute("SELECT count(*) FROM memory_jobs WHERE owner_id=?", (owner,)).fetchone()[0]
        return {"policy": self.policy(owner), "units": self.units(owner),
                "results": self.recall(owner, query, peer_id=peer_id) if query or peer_id else [],
                "pending_sources": len(self.sources(owner)), "last_job": dict(row) if row else None,
                "extraction_attempts": calls, "categories": list(CATEGORIES),
                "engine": "local_rules", "external_processing": False}

    def remember(self, owner, payload):
        """Human-selected notes can use any accessible source, even after a batch."""
        sources = {s["key"]: s for s in self.sources(owner, pending_only=False)}
        with self.store.db() as db:
            people = [dict(r) for r in db.execute("SELECT id,name FROM members")]
        source_key = payload.get("source_key")
        if not isinstance(source_key, str) or source_key not in sources:
            raise AppError("Conversation source not found", 404)
        unit = self.validate({"summary": payload.get("summary"), "category": payload.get("category"),
            "importance": payload.get("importance", .8), "reported_origin": payload.get("reported_origin", ""),
            "keywords": payload.get("keywords", []), "subject_id": payload.get("subject_id"),
            "reason": "Selected by the resident", "evidence": [{"source_key": source_key, "quote": payload.get("quote")}]},
            owner, sources, people)
        policy = self.policy(owner)
        if excluded(json.dumps(unit), policy):
            raise AppError("This note contains a phrase excluded by your memory priorities")
        with self.store.db() as db:
            if not self.save_unit(db, owner, unit, set()):
                raise AppError("This note was hidden earlier; restore it before saving the same statement again", 409)
        return {"ok": True}


# Local extraction deliberately retains the speaker's words. It does not pretend
# to resolve pronouns, interpret arbitrary instructions, or infer hidden beliefs.
RULES = (
    ("priorities", r"\b(priorit(?:y|ies|i[sz]e|i[sz]ing)|my main focus|our main focus|most important to (?:me|us))\b"),
    ("commitments", r"\b(I will|I'll|we will|we'll|I promise|committed to|deadline)\b"),
    ("requests", r"\b(I need|we need|looking for|can you|could you|seeking|want help)\b"),
    ("offers", r"\b(I can|we can|can offer|happy to help|available to|offering)\b"),
    ("skills", r"\b(experience|expertise|skilled|speciali[sz]e|engineer|researcher|programmer|CV)\b"),
    ("interests", r"\b(interested|enjoy|love|curious|hobby|passion)\b"),
    ("disagreements", r"\b(disagree|oppose|concern|object to)\b"),
    ("ideas", r"\b(suggest|suggested|idea|perhaps|proposal|pseudocode|prototype|code|solution)\b"),
    ("relationships", r"\b(introduce|introduction|connect|collaborat|know each other)\w*"),
    ("logistics", r"\b(meet|tomorrow|today|Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday|o'clock)\b"),
)


def local_extract(owner, job_id, payload):
    policy = payload["priorities"]
    names = {p["id"]: p["name"] for p in payload["people"]}
    candidates = []
    for source in payload["sources"]:
        for sentence in re.split(r"(?<=[.!?])\s+|\n+", source["body"]):
            # Long code/text spans stay accessible as sources for manual notes.
            sentence = sentence.strip()
            if not 12 <= len(sentence) <= 700:
                continue
            category = next((cat for cat, pattern in RULES if re.search(pattern, sentence, re.I)), "facts")
            if policy["weights"][category] == 0:
                continue
            topic_hits = sum(bool(terms(topic) & terms(sentence)) for topic in policy["topics"])
            priority_hits = len(terms(policy["instructions"]) & terms(sentence))
            importance = min(.95, .35 + .12 * topic_hits + .02 * min(priority_hits, 5)
                             + (.15 if category in ("commitments", "requests", "offers") else 0))
            origin = ""
            if source["speaker_id"] != "hermes":
                for person in sorted(payload["people"], key=lambda p: len(p["name"]), reverse=True):
                    if person["id"] in (owner, source["speaker_id"]):
                        continue
                    pattern = r"(?<!\w)" + re.escape(person["name"]) + r"\s+(?:(?:has|had)\s+)?(?:said|says|told|mentioned|suggested|shared|recommended)\b"
                    if re.search(pattern, sentence, re.I) or re.search(r"\baccording to\s+" + re.escape(person["name"]) + r"(?!\w)", sentence, re.I):
                        origin = person["name"]
                        break
            speaker = names.get(source["speaker_id"], "Hermes draft")
            unit = {"summary": f"{speaker}: {sentence}", "category": category,
                "importance": importance, "reported_origin": origin,
                "keywords": sorted((t for t in terms(sentence) if len(t) <= 60), key=lambda t: (-len(t), t))[:12],
                "reason": f"Local rule: {category}; {topic_hits} topic matches; {priority_hits} priority-word matches.",
                "evidence": [{"source_key": source["key"], "quote": sentence}]}
            # Only exact, attributed duplicates consolidate automatically.
            candidates.append((policy["weights"][category] * importance, unit))
    selected, seen = [], set()
    for _, unit in sorted(candidates, key=lambda pair: pair[0], reverse=True):
        signature = (unit["summary"], unit["evidence"][0]["source_key"])
        if signature not in seen:
            selected.append(unit)
            seen.add(signature)
        if len(selected) == MAX_UNITS:
            break
    return selected
