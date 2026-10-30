"""Transactional residency state; deliberately independent of experiment stores."""
from contextlib import contextmanager
import hashlib
import hmac
import re
import secrets
import sqlite3
import time
import uuid


class AppError(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def text(value, field, maximum=4000, required=True):
    if not isinstance(value, str):
        raise AppError(f"{field} must be text")
    value = value.strip()
    if (required and not value) or len(value) > maximum or "\x00" in value:
        raise AppError(f"{field} must contain {'1' if required else '0'}–{maximum} characters")
    return value


def password_hash(password, salt):
    return hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1).hex()


def digest(token):
    return hashlib.sha256(token.encode()).hexdigest()


PUBLIC_MEMBER = "id, name, bio, seeking, offering, created_at"


class Store:
    def __init__(self, settings):
        self.settings = settings
        settings.data_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.path = settings.data_dir / "residency.sqlite3"
        with self.db() as db:
            # Readers (dashboards/recall) must not block commits by agent and
            # memory workers. WAL is persistent and also applies on reopen.
            if db.execute("PRAGMA journal_mode=WAL").fetchone()[0].lower() != 'wal':
                raise RuntimeError('Residency database requires WAL concurrency')
            db.executescript("""
                CREATE TABLE IF NOT EXISTS metadata(key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS members(
                    id TEXT PRIMARY KEY, email TEXT UNIQUE NOT NULL, name TEXT NOT NULL,
                    salt TEXT NOT NULL, password_hash TEXT NOT NULL,
                    bio TEXT NOT NULL DEFAULT '', seeking TEXT NOT NULL DEFAULT '',
                    offering TEXT NOT NULL DEFAULT '', created_at REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS sessions(
                    token_hash TEXT PRIMARY KEY, member_id TEXT NOT NULL REFERENCES members(id),
                    csrf TEXT NOT NULL, expires_at REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS problems(
                    id TEXT PRIMARY KEY, member_id TEXT NOT NULL REFERENCES members(id),
                    title TEXT NOT NULL, body TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'open',
                    created_at REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS comments(
                    id TEXT PRIMARY KEY, problem_id TEXT NOT NULL REFERENCES problems(id),
                    member_id TEXT NOT NULL REFERENCES members(id), body TEXT NOT NULL,
                    created_at REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS messages(
                    id TEXT PRIMARY KEY, sender_id TEXT NOT NULL REFERENCES members(id),
                    recipient_id TEXT NOT NULL REFERENCES members(id), body TEXT NOT NULL,
                    created_at REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS assistant_turns(
                    id TEXT PRIMARY KEY, member_id TEXT NOT NULL REFERENCES members(id),
                    prompt TEXT NOT NULL, reply TEXT, status TEXT NOT NULL,
                    error TEXT, created_at REAL NOT NULL);
                CREATE UNIQUE INDEX IF NOT EXISTS one_pending_turn
                    ON assistant_turns(member_id) WHERE status='pending';
                CREATE INDEX IF NOT EXISTS messages_participants ON messages(sender_id, recipient_id);
                CREATE TABLE IF NOT EXISTS introductions(
                    id TEXT PRIMARY KEY, member_id TEXT UNIQUE NOT NULL REFERENCES members(id),
                    body TEXT NOT NULL, created_at REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS conversations(
                    id TEXT PRIMARY KEY, created_by TEXT NOT NULL REFERENCES members(id), created_at REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS conversation_messages(
                    seq INTEGER PRIMARY KEY AUTOINCREMENT, id TEXT UNIQUE NOT NULL,
                    conversation_id TEXT NOT NULL REFERENCES conversations(id),
                    sender_id TEXT NOT NULL REFERENCES members(id), body TEXT NOT NULL, created_at REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS conversation_visits(
                    id TEXT PRIMARY KEY, conversation_id TEXT NOT NULL REFERENCES conversations(id),
                    member_id TEXT NOT NULL REFERENCES members(id), joined_after_seq INTEGER NOT NULL,
                    left_after_seq INTEGER, joined_at REAL NOT NULL, left_at REAL);
                CREATE UNIQUE INDEX IF NOT EXISTS one_active_conversation_visit
                    ON conversation_visits(conversation_id,member_id) WHERE left_after_seq IS NULL;
                CREATE INDEX IF NOT EXISTS conversation_visibility ON conversation_visits(member_id,conversation_id);
                CREATE INDEX IF NOT EXISTS conversation_message_order ON conversation_messages(conversation_id,seq);
            """)
            from .memory import create_schema
            create_schema(db)
            db.execute("INSERT OR IGNORE INTO metadata VALUES('instance_id', ?)", (uuid.uuid4().hex,))
            self.instance_id = db.execute("SELECT value FROM metadata WHERE key='instance_id'").fetchone()[0]
            db.execute("UPDATE assistant_turns SET status='failed', error='App restarted during this request; execution at Hermes is unknown.' WHERE status='pending'")
        self.path.chmod(0o600)

    @contextmanager
    def db(self):
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        try:
            with db:
                yield db
        finally:
            db.close()

    def register(self, payload):
        if not isinstance(payload.get("join_code"), str) or not hmac.compare_digest(
                payload["join_code"].encode(), self.settings.join_code.encode()):
            raise AppError("Invalid residency invitation code", 403)
        email = text(payload.get("email"), "Email", 254).lower()
        if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email):
            raise AppError("Enter a valid email address")
        name = text(payload.get("name"), "Name", 80)
        password = payload.get("password")
        if not isinstance(password, str) or not 12 <= len(password) <= 256:
            raise AppError("Use a password with 12–256 characters")
        profile = {k: text(payload.get(k, ""), k, 2000, False) for k in ("bio", "seeking", "offering")}
        salt = secrets.token_hex(16)
        hashed = password_hash(password, salt)
        member_id = uuid.uuid4().hex
        try:
            with self.db() as db:
                db.execute("INSERT INTO members VALUES(?,?,?,?,?,?,?,?,?)", (
                    member_id, email, name, salt, hashed, profile["bio"], profile["seeking"],
                    profile["offering"], time.time()))
        except sqlite3.IntegrityError:
            raise AppError("An account with this email already exists", 409) from None
        return self.new_session(member_id)

    def login(self, payload):
        email = text(payload.get("email"), "Email", 254).lower()
        password = payload.get("password")
        if not isinstance(password, str) or len(password) > 256:
            raise AppError("Invalid email or password", 401)
        with self.db() as db:
            member = db.execute("SELECT * FROM members WHERE email=?", (email,)).fetchone()
        # Do equal-cost work for missing accounts as well.
        hashed = password_hash(password, member["salt"] if member else "00" * 16)
        if not member or not hmac.compare_digest(hashed, member["password_hash"]):
            raise AppError("Invalid email or password", 401)
        return self.new_session(member["id"])

    def new_session(self, member_id):
        token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        with self.db() as db:
            db.execute("DELETE FROM sessions WHERE expires_at<=?", (time.time(),))
            db.execute("INSERT INTO sessions VALUES(?,?,?,?)", (
                digest(token), member_id, csrf, time.time() + self.settings.session_seconds))
        return token, csrf

    def authenticate(self, token):
        with self.db() as db:
            row = db.execute("SELECT member_id, csrf FROM sessions WHERE token_hash=? AND expires_at>?",
                             (digest(token), time.time())).fetchone()
        if not row:
            raise AppError("Please sign in", 401)
        return dict(row)

    def logout(self, token):
        with self.db() as db:
            db.execute("DELETE FROM sessions WHERE token_hash=?", (digest(token),))

    def snapshot(self, member_id):
        with self.db() as db:
            me = dict(db.execute(f"SELECT {PUBLIC_MEMBER}, email FROM members WHERE id=?", (member_id,)).fetchone())
            members = [dict(r) for r in db.execute(f"SELECT {PUBLIC_MEMBER} FROM members ORDER BY created_at")]
            problems = [dict(r) for r in db.execute("SELECT * FROM problems ORDER BY created_at DESC")]
            comments = [dict(r) for r in db.execute("SELECT * FROM comments ORDER BY created_at")]
            messages = [dict(r) for r in db.execute("SELECT * FROM messages WHERE sender_id=? OR recipient_id=? ORDER BY created_at", (member_id, member_id))]
            turns = [dict(r) for r in db.execute("SELECT * FROM assistant_turns WHERE member_id=? ORDER BY created_at", (member_id,))]
        return dict(me=me, members=members, problems=problems, comments=comments,
                    messages=messages, assistant_turns=turns,
                    introductions=self.introductions(), **self.conversation_state(member_id))

    def introductions(self):
        with self.db() as db:
            return [dict(r) for r in db.execute('SELECT * FROM introductions ORDER BY created_at,id')]

    def introduce(self, member_id, payload):
        item = {'id': uuid.uuid4().hex, 'member_id': member_id,
                'body': text(payload.get('body'), 'Introduction', 2000), 'created_at': time.time()}
        try:
            with self.db() as db:
                db.execute('INSERT INTO introductions VALUES(:id,:member_id,:body,:created_at)', item)
        except sqlite3.IntegrityError:
            raise AppError('You have already posted your introduction', 409) from None
        return item

    def conversation_state(self, member_id):
        with self.db() as db:
            rooms = [dict(r) for r in db.execute('SELECT * FROM conversations ORDER BY created_at,id')]
            participants = {}
            for row in db.execute('SELECT conversation_id,member_id FROM conversation_visits WHERE left_after_seq IS NULL'):
                participants.setdefault(row['conversation_id'], []).append(row['member_id'])
            visits = [dict(r) for r in db.execute('SELECT * FROM conversation_visits WHERE member_id=?', (member_id,))]
            # Sequence windows, rather than timestamps, define what the resident witnessed.
            messages = [dict(r) for r in db.execute('''SELECT m.* FROM conversation_messages m
                WHERE EXISTS(SELECT 1 FROM conversation_visits v
                    WHERE v.member_id=? AND v.conversation_id=m.conversation_id
                    AND m.seq>v.joined_after_seq AND (v.left_after_seq IS NULL OR m.seq<=v.left_after_seq))
                ORDER BY m.seq''', (member_id,))]
        for room in rooms:
            room['participants'] = sorted(participants.get(room['id'], []))
            room['joined'] = any(v['conversation_id'] == room['id'] and v['left_after_seq'] is None for v in visits)
        return {'conversations': rooms, 'conversation_messages': messages}

    @staticmethod
    def _join_conversation(db, conversation_id, member_id):
        if not db.execute('SELECT 1 FROM conversations WHERE id=?', (conversation_id,)).fetchone():
            raise AppError('Conversation not found', 404)
        if db.execute('SELECT 1 FROM conversation_visits WHERE conversation_id=? AND member_id=? AND left_after_seq IS NULL',
                      (conversation_id, member_id)).fetchone():
            return
        boundary = db.execute('SELECT coalesce(max(seq),0) FROM conversation_messages').fetchone()[0]
        db.execute('INSERT INTO conversation_visits VALUES(?,?,?,?,NULL,?,NULL)',
                   (uuid.uuid4().hex, conversation_id, member_id, boundary, time.time()))

    def conversation_action(self, member_id, payload, *, reuse_direct_rooms=None):
        """Apply a bounded action atomically; only active members may speak/leave.

        Presence (room ID and active participants) is public. Message text is only
        visible within the resident's joined intervals, including after leaving.
        """
        allowed = {'start_conversations', 'join_conversations', 'messages', 'leave_conversations'}
        if not isinstance(payload, dict) or set(payload) - allowed:
            raise AppError('Invalid conversation action')
        arrays = {key: payload.get(key, []) for key in allowed}
        if any(not isinstance(value, list) or len(value) > 3 for value in arrays.values()):
            raise AppError('Use at most three items per conversation action')
        created, delivered, affected = [], [], {member_id}
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            # Opt-in live-event continuation. Match only rooms in this event
            # with exactly these two active participants; never move a private
            # opening into a group room or reveal history across a leave gap.
            direct_pairs = {}
            if reuse_direct_rooms:
                active = {}
                for visit in db.execute('SELECT conversation_id,member_id FROM conversation_visits WHERE left_after_seq IS NULL'):
                    if visit['conversation_id'] in reuse_direct_rooms:
                        active.setdefault(visit['conversation_id'],set()).add(visit['member_id'])
                for room, participants in sorted(active.items()):
                    if len(participants)==2:direct_pairs.setdefault(frozenset(participants),room)
            for item in arrays['start_conversations']:
                if not isinstance(item, dict) or set(item) - {'with', 'body'}:
                    raise AppError('Invalid new conversation')
                supplied=item.get('with');peers=supplied if isinstance(supplied,list) else [supplied]
                if not 1<=len(peers)<=50 or any(not isinstance(peer,str) for peer in peers) or len(set(peers))!=len(peers):raise AppError('Choose one to fifty distinct other residents')
                peers=[text(peer,'Resident',64) for peer in peers]
                if len(set(peers))!=len(peers):raise AppError('Choose distinct other residents')
                if any(peer==member_id or not db.execute('SELECT 1 FROM members WHERE id=?',(peer,)).fetchone() for peer in peers):raise AppError('Choose other known residents',400)
                pair=frozenset((member_id,*peers))
                # A group opening never reuses a DM or copies its private history.
                room_id=direct_pairs.get(pair) if len(peers)==1 and reuse_direct_rooms is not None else None
                if room_id is None:
                    room_id = uuid.uuid4().hex
                    db.execute('INSERT INTO conversations VALUES(?,?,?)', (room_id, member_id, time.time()))
                    self._join_conversation(db, room_id, member_id)
                    for peer in peers:self._join_conversation(db, room_id, peer)
                    created.append(room_id)
                    if len(peers)==1 and reuse_direct_rooms is not None:direct_pairs[pair]=room_id
                affected.update(peers)
                if item.get('body') is not None:
                    delivered.append(self._conversation_message(db, room_id, member_id, item['body']))
            for room_id in arrays['join_conversations']:
                self._join_conversation(db, text(room_id, 'Conversation', 64), member_id)
            for item in arrays['messages']:
                if not isinstance(item, dict) or set(item) != {'conversation_id', 'body'}:
                    raise AppError('Invalid conversation message')
                room_id = text(item['conversation_id'], 'Conversation', 64)
                delivered.append(self._conversation_message(db, room_id, member_id, item['body']))
                affected.update(r[0] for r in db.execute('SELECT member_id FROM conversation_visits WHERE conversation_id=? AND left_after_seq IS NULL', (room_id,)))
            for room_id in arrays['leave_conversations']:
                room_id = text(room_id, 'Conversation', 64)
                boundary = db.execute('SELECT coalesce(max(seq),0) FROM conversation_messages').fetchone()[0]
                updated = db.execute('''UPDATE conversation_visits SET left_after_seq=?,left_at=?
                    WHERE conversation_id=? AND member_id=? AND left_after_seq IS NULL''',
                    (boundary, time.time(), room_id, member_id))
                if not updated.rowcount:
                    raise AppError('You are not in that conversation', 403)
        return {'created_conversations': created, 'messages': delivered, 'affected_members': sorted(affected)}

    @staticmethod
    def _conversation_message(db, room_id, member_id, body):
        body = text(body, 'Message', 8000)
        if not db.execute('SELECT 1 FROM conversation_visits WHERE conversation_id=? AND member_id=? AND left_after_seq IS NULL',
                          (room_id, member_id)).fetchone():
            raise AppError('Join the conversation before sending a message', 403)
        item = {'id': uuid.uuid4().hex, 'conversation_id': room_id, 'sender_id': member_id,
                'body': body, 'created_at': time.time()}
        cursor = db.execute('''INSERT INTO conversation_messages(id,conversation_id,sender_id,body,created_at)
            VALUES(:id,:conversation_id,:sender_id,:body,:created_at)''', item)
        return {**item, 'seq': cursor.lastrowid}

    def update_profile(self, member_id, payload):
        name = text(payload.get("name"), "Name", 80)
        profile = [text(payload.get(k, ""), k, 2000, False) for k in ("bio", "seeking", "offering")]
        with self.db() as db:
            db.execute("UPDATE members SET name=?,bio=?,seeking=?,offering=? WHERE id=?", (name, *profile, member_id))

    def problem(self, member_id, payload):
        title = text(payload.get("title"), "Title", 160)
        body = text(payload.get("body"), "Problem", 8000)
        item = dict(id=uuid.uuid4().hex, member_id=member_id, title=title, body=body,
                    status="open", created_at=time.time())
        with self.db() as db:
            db.execute("INSERT INTO problems VALUES(:id,:member_id,:title,:body,:status,:created_at)", item)
        return item

    def resolve(self, member_id, problem_id, status):
        if status not in ("open", "solved"):
            raise AppError("Status must be open or solved")
        with self.db() as db:
            row = db.execute("SELECT member_id FROM problems WHERE id=?", (problem_id,)).fetchone()
            if not row:
                raise AppError("Problem not found", 404)
            if row[0] != member_id:
                raise AppError("Only the author can change this problem's status", 403)
            db.execute("UPDATE problems SET status=? WHERE id=?", (status, problem_id))

    def comment(self, member_id, problem_id, payload):
        body = text(payload.get("body"), "Comment", 8000)
        item = dict(id=uuid.uuid4().hex, problem_id=problem_id, member_id=member_id,
                    body=body, created_at=time.time())
        with self.db() as db:
            if not db.execute("SELECT 1 FROM problems WHERE id=?", (problem_id,)).fetchone():
                raise AppError("Problem not found", 404)
            db.execute("INSERT INTO comments VALUES(:id,:problem_id,:member_id,:body,:created_at)", item)
        return item

    def message(self, member_id, payload):
        recipient = text(payload.get("recipient_id"), "Recipient", 64)
        body = text(payload.get("body"), "Message", 8000)
        if recipient == member_id:
            raise AppError("Choose another resident")
        item = dict(id=uuid.uuid4().hex, sender_id=member_id, recipient_id=recipient,
                    body=body, created_at=time.time())
        with self.db() as db:
            if not db.execute("SELECT 1 FROM members WHERE id=?", (recipient,)).fetchone():
                raise AppError("Resident not found", 404)
            db.execute("INSERT INTO messages VALUES(:id,:sender_id,:recipient_id,:body,:created_at)", item)
        return item

    def begin_turn(self, member_id, prompt):
        prompt = text(prompt, "Message", 8000)
        turn_id = uuid.uuid4().hex
        try:
            with self.db() as db:
                db.execute("INSERT INTO assistant_turns VALUES(?,?,?,NULL,'pending',NULL,?)",
                           (turn_id, member_id, prompt, time.time()))
        except sqlite3.IntegrityError:
            raise AppError("Your previous Hermes request is still running", 409) from None
        return turn_id

    def finish_turn(self, turn_id, reply=None, error=None):
        with self.db() as db:
            db.execute("UPDATE assistant_turns SET reply=?,error=?,status=? WHERE id=?",
                       (reply, error, "failed" if error else "completed", turn_id))
