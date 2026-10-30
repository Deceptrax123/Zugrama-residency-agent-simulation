"""Standalone HTTP application for a small, trusted residency cohort."""
import argparse
from collections import defaultdict, deque
import fcntl
import hmac
from http.cookies import SimpleCookie, CookieError
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import logging
from pathlib import Path
import signal
import threading
import time
from urllib.parse import parse_qs, urlsplit

from .config import Settings
from .hermes import Hermes
from .store import AppError, Store
from .memory import AUTOMATIC_BATCH_KINDS, ConversationMemory, local_extract

PUBLIC = Path(__file__).parent / "public"


class ResidencyServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address, settings, hermes=None):
        self.settings = settings
        self.attempts = defaultdict(deque)
        self.rate_lock = threading.Lock()
        self.health_lock = threading.Lock()
        self.health_at = 0
        self.health_value = None
        self.data_lock = None
        self.event = None
        self.sandbox = None
        self.semantic = None
        self.cycle = None
        settings.data_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.data_lock = (settings.data_dir / "app.lock").open("a")
        try:
            fcntl.flock(self.data_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.store = Store(settings)
            self.memory = ConversationMemory(self.store)
            self.hermes = hermes or Hermes(settings)
            super().__init__(address, Handler)
        except Exception:
            self.data_lock.close()
            raise

    def server_close(self):
        if getattr(self,'insight_analysis',None):self.insight_analysis.close()
        if self.cycle:self.cycle.close()
        if self.event: self.event.close()
        if self.semantic:self.semantic.close()
        super().server_close()
        if self.data_lock:
            self.data_lock.close()

    def health(self):
        with self.health_lock:
            if time.monotonic() - self.health_at > 15 or self.health_value is None:
                self.health_value = self.hermes.health()
                self.health_at = time.monotonic()
            return self.health_value

    def rate_limit(self, key, maximum=12, seconds=60):
        now = time.monotonic()
        with self.rate_lock:
            # Periodically drop idle keys so unauthenticated traffic cannot grow this forever.
            if len(self.attempts) > 1000:
                self.attempts = defaultdict(deque, {k: v for k, v in self.attempts.items() if v and now - v[-1] < seconds})
            attempts = self.attempts[key]
            while attempts and now - attempts[0] > seconds:
                attempts.popleft()
            if len(attempts) >= maximum:
                raise AppError("Too many requests. Please wait a minute.", 429)
            attempts.append(now)

    def local_memory_after_write(self, member_id):
        # Optional local batches never affect delivery of the original write.
        try:
            if self.memory.should_process(member_id):
                self.memory.process(member_id, local_extract, source_kinds=AUTOMATIC_BATCH_KINDS)
        except Exception:
            pass  # Visible in the resident's memory job status; no retry loop.

    def capture_conversations(self, members):
        for member_id in members:
            try:
                self.memory.capture_conversations(member_id)
            except Exception:
                pass  # Delivery remains durable; any failed extraction job is inspectable.
        if self.semantic:self.semantic.enqueue(members)


class Handler(BaseHTTPRequestHandler):
    server_version = "Residency/1"

    def setup(self):
        super().setup()
        self.connection.settimeout(15)

    def log_message(self, format, *args):
        # Never log credentials, bodies, or query strings.
        pass

    def respond(self, body, status=200, mime="application/json", cookie=None):
        if mime == "application/json":
            body = json.dumps(body, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", mime + "; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self' data:; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'")
        if cookie:
            self.send_header("Set-Cookie", cookie)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def cookie(self, token, clear=False):
        value = f"residency_session={token}; Path=/; HttpOnly; SameSite=Strict; Max-Age={0 if clear else self.server.settings.session_seconds}"
        if self.server.settings.secure_cookies:
            value += "; Secure"
        return value

    def token(self):
        cookie = SimpleCookie()
        try:
            cookie.load(self.headers.get("Cookie", ""))
        except CookieError:
            raise AppError("Invalid session cookie", 401) from None
        return cookie["residency_session"].value if "residency_session" in cookie else ""

    def origin_check(self):
        expected = self.server.settings.public_origin.rstrip("/")
        if self.headers.get("Host") != urlsplit(expected).netloc:
            raise AppError("Unrecognized host", 403)
        origin = self.headers.get("Origin")
        if origin and origin != expected:
            raise AppError("Cross-origin requests are disabled", 403)
        if self.headers.get("Sec-Fetch-Site") == "cross-site":
            raise AppError("Cross-site requests are disabled", 403)

    def read_body(self, maximum=65536):
        if self.headers.get("Content-Type", "").split(";")[0].strip() != "application/json":
            raise AppError("Use application/json", 415)
        if self.headers.get("Transfer-Encoding"):
            raise AppError("Transfer-Encoding is unsupported")
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            raise AppError("Invalid Content-Length") from None
        if length < 0 or length > maximum:
            raise AppError("Request body exceeds the permitted size", 413)
        try:
            raw = self.rfile.read(length)
            if len(raw) != length:
                raise ValueError()
            body = json.loads(raw)
        except (ValueError, UnicodeError):
            raise AppError("Invalid JSON body") from None
        if not isinstance(body, dict):
            raise AppError("JSON body must be an object")
        return body

    def handle_request(self):
        try:
            self.origin_check()
            path = urlsplit(self.path).path
            method = "GET" if self.command == "HEAD" else self.command
            if method == "GET" and path in ("/", "/app.js", "/styles.css"):
                name, mime = {"/": ("index.html", "text/html"), "/app.js": ("app.js", "text/javascript"),
                              "/styles.css": ("styles.css", "text/css")}[path]
                content=(PUBLIC/name).read_bytes()
                if name=='index.html' and getattr(self.server.sandbox,'live_cohort',False):content=content.replace(b'Commonroom',b'Zugrama')
                return self.respond(content,mime=mime)
            if method == "GET" and path == "/healthz":
                return self.respond({"status": "ok", "app": "residency"})
            if method not in ("GET", "POST", "PATCH"):
                raise AppError("Method not allowed", 405)
            maximum = 65536
            if self.server.sandbox and path == '/api/sandbox/identity/extract/pdf':
                from .cv_pdf import MAX_ENCODED
                maximum = MAX_ENCODED + 1024
            elif self.server.sandbox and path == '/api/sandbox/agents':
                maximum = 131072
            elif self.server.sandbox and path in ('/api/sandbox/identity/review','/api/sandbox/identity/submit'):
                maximum = 524288
            elif self.server.sandbox and path in ('/api/sandbox/onboarding/import','/api/cohort/import/preview','/api/cohort/import/confirm'):
                maximum = 5*1024*1024
            payload = self.read_body(maximum) if method in ("POST", "PATCH") else {}
            store = self.server.store
            if method == 'GET' and path == '/api/setup':
                return self.respond({'identity_test': bool(self.server.sandbox),'live_cohort':bool(getattr(self.server.sandbox,'live_cohort',False)),
                                     'host_signup_available': bool(self.server.sandbox and not self.server.sandbox.owner)})
            if method == "POST" and path in ("/api/join", "/api/login"):
                self.server.rate_limit(("auth", self.client_address[0]))
                token, csrf = ((self.server.sandbox.signup(payload) if self.server.sandbox else store.register(payload)) if path == "/api/join" else store.login(payload))
                if path == '/api/join':
                    self.server.capture_conversations([store.authenticate(token)['member_id']])
                return self.respond({"csrf": csrf}, 201 if path == "/api/join" else 200, cookie=self.cookie(token))
            session = store.authenticate(self.token())
            member_id = session["member_id"]
            if method != "GET":
                supplied = self.headers.get("X-CSRF-Token", "")
                if not hmac.compare_digest(supplied.encode(), session["csrf"].encode()):
                    raise AppError("Session verification failed. Reload and try again.", 403)
                self.server.rate_limit(("write", member_id), maximum=60)
            if method == "GET" and path == "/api/state":
                return self.respond({**store.snapshot(member_id), "csrf": session["csrf"],
                                     "memory": self.server.memory.view(member_id),
                                     'sandbox':self.server.sandbox.status(member_id) if self.server.sandbox else None,
                                     'cycle':self.server.cycle.view(member_id) if self.server.cycle else None,
                                     'semantic':self.server.semantic.view() if self.server.semantic else None,
                                     'event':self.server.event.status(member_id) if self.server.event else None})
            if path in ('/api/cohort/import/preview','/api/cohort/import/confirm') and method=='POST' and getattr(self.server.sandbox,'live_cohort',False):
                return self.respond(self.server.sandbox.preview_import(member_id,payload) if path.endswith('/preview') else self.server.sandbox.apply_import(member_id,payload))
            if path == '/api/sandbox/agents' and method == 'POST' and self.server.sandbox:
                if set(payload) != {'slot', 'identity'}:
                    raise AppError('Provide an agent slot and identity')
                return self.respond(self.server.sandbox.save_agent(member_id, payload['slot'], payload['identity']))
            if self.server.sandbox and path == '/api/agent-accounts' and method == 'GET':
                return self.respond(self.server.sandbox.accounts.view(member_id))
            if self.server.sandbox and path=='/api/agent-memory/policy' and method=='POST':
                self.server.sandbox.authorize(member_id)
                if set(payload)!={'owner_id','network_context'} or type(payload['network_context']) is not bool:raise AppError('Choose an agent and its memory-context preference')
                owner=self.server.sandbox.accounts.owner(payload['owner_id'])
                return self.respond(self.server.memory.set_policy(owner,{'network_context':payload['network_context']}))
            if self.server.sandbox and path == '/api/agent-budget' and method == 'POST':
                return self.respond(self.server.sandbox.accounts.configure(member_id,payload))
            if self.server.sandbox and path == '/api/agent-requests' and method == 'POST':
                return self.respond(self.server.sandbox.accounts.message(member_id,payload))
            if self.server.sandbox and path == '/api/sandbox/onboarding/import' and method == 'POST':
                self.server.sandbox.authorize(member_id)
                from .onboarding import prepare
                return self.respond(prepare(payload))
            if path == '/api/sandbox/identity/extract' and method == 'POST' and self.server.sandbox:
                self.server.sandbox.authorize(member_id)
                self.server.rate_limit(('cv-extraction', member_id), maximum=6)
                return self.respond(self.server.sandbox.extract_cv(member_id, payload))
            if path == '/api/sandbox/identity/extract/pdf' and method == 'POST' and self.server.sandbox:
                self.server.sandbox.authorize(member_id)
                self.server.rate_limit(('cv-extraction', member_id), maximum=6)
                return self.respond(self.server.sandbox.extract_pdf(member_id, payload))
            if path == '/api/sandbox/identity/extract/website' and method == 'POST' and self.server.sandbox:
                self.server.sandbox.authorize(member_id)
                self.server.rate_limit(('cv-extraction',member_id),maximum=6)
                return self.respond(self.server.sandbox.extract_website(member_id,payload))
            if path == '/api/sandbox/identity' and method == 'GET' and self.server.sandbox:
                query=parse_qs(urlsplit(self.path).query)
                return self.respond(self.server.sandbox.export_identity(member_id,query.get('slot',[''])[0]))
            if path in ('/api/sandbox/identity/review','/api/sandbox/identity/submit') and method == 'POST' and self.server.sandbox:
                return self.respond(self.server.sandbox.review_identity(member_id,payload) if path.endswith('/review')
                                    else self.server.sandbox.submit_identity(member_id,payload))
            if path == '/api/sandbox/compass' and method == 'POST' and self.server.sandbox:
                return self.respond(self.server.sandbox.observe_compass(member_id, payload))
            if path == '/api/agent-memory' and method == 'GET' and self.server.semantic:
                query=parse_qs(urlsplit(self.path).query)
                return self.respond(self.server.semantic.search(member_id,query.get('agent',[''])[0],query.get('q',[''])[0]))
            if path == '/api/agent-notes' and method == 'GET' and self.server.semantic:
                return self.respond(self.server.semantic.notes(member_id))
            if path == '/api/agent-memory/document' and method == 'GET' and self.server.semantic:
                query=parse_qs(urlsplit(self.path).query)
                return self.respond(self.server.semantic.export_markdown(member_id,query.get('agent',[''])[0]))
            if path in ('/api/day-cycle/sleep','/api/day-cycle/next') and method == 'POST' and self.server.cycle:
                if payload:raise AppError('This day transition does not accept settings')
                return self.respond(self.server.cycle.before_sleep(member_id) if path.endswith('/sleep') else self.server.cycle.next_day(member_id))
            if path == '/api/event/graph' and method == 'GET' and self.server.event:
                from .graph import communication_graph
                query = parse_qs(urlsplit(self.path).query)
                return self.respond(communication_graph(self.server.event, member_id,
                    query.get('window', ['300'])[0], query.get('offset', [None])[0]))
            if path == '/api/analysis/start' and method == 'POST' and getattr(self.server,'insight_analysis',None):
                return self.respond(self.server.insight_analysis.start(member_id,payload))
            if path == '/api/analysis' and method == 'GET' and getattr(self.server,'insight_analysis',None):
                self.server.sandbox.authorize(member_id)
                return self.respond(self.server.insight_analysis.status())
            if path == '/api/event/resume' and method == 'POST' and self.server.event:
                if payload!={'confirmed':True}:raise AppError('Confirm that credits or quota are available before resuming')
                return self.respond(self.server.event.resume(member_id))
            if path == '/api/event/agent/restart' and method == 'POST' and self.server.event:
                return self.respond(self.server.event.restart_agent(member_id,payload))
            if path == '/api/event/start' and method == 'POST' and self.server.sandbox:
                return self.respond(self.server.sandbox.start(member_id, payload))
            if path == '/api/event' and method == 'GET' and self.server.event:
                return self.respond(self.server.event.status(member_id))
            if path in ('/api/event/start','/api/event/stop') and method == 'POST' and self.server.event:
                if path.endswith('/stop') and self.server.cycle and self.server.cycle.state['enabled']:
                    return self.respond(self.server.cycle.abort(member_id))
                result = self.server.event.start(member_id,payload) if path.endswith('/start') else self.server.event.stop(member_id)
                return self.respond(result)
            if method == "GET" and path == "/api/memory":
                query = parse_qs(urlsplit(self.path).query)
                return self.respond(self.server.memory.view(member_id, query.get("q", [""])[0][:1000], query.get("peer", [None])[0]))
            if method == "GET" and path == "/api/memory/sources":
                return self.respond({"sources": self.server.memory.sources(member_id, pending_only=False)})
            if method == "PATCH" and path == "/api/memory/policy":
                return self.respond(self.server.memory.set_policy(member_id, payload))
            if method == "POST" and path == "/api/memory/extract":
                self.server.rate_limit(("memory", member_id), maximum=6)
                return self.respond(self.server.memory.process(member_id, local_extract))
            if method == "POST" and path == "/api/memory/notes":
                return self.respond(self.server.memory.remember(member_id, payload), 201)
            if method == "PATCH" and path.startswith("/api/memory/notes/"):
                self.server.memory.update_unit(member_id, path.rsplit("/", 1)[-1], payload)
                return self.respond({"ok": True})
            if method == "GET" and path == "/api/hermes/status":
                return self.respond(self.server.health())
            if method == "POST" and path == "/api/logout":
                store.logout(self.token())
                return self.respond({"ok": True}, cookie=self.cookie("", clear=True))
            if method == "PATCH" and path == "/api/profile":
                store.update_profile(member_id, payload)
                return self.respond({"ok": True})
            if method == "POST" and path == "/api/problems":
                result = store.problem(member_id, payload)
                self.server.local_memory_after_write(member_id)
                return self.respond(result, 201)
            parts = path.strip("/").split("/")
            if path == '/api/introductions' and method == 'POST':
                result = store.introduce(member_id, payload)
                self.server.capture_conversations([person['id'] for person in store.snapshot(member_id)['members']])
                return self.respond(result, 201)
            if path == '/api/conversations' and method == 'GET':
                return self.respond(store.conversation_state(member_id))
            if path == '/api/conversations/actions' and method == 'POST':
                if self.server.sandbox:
                    raise AppError('The test host observes; the three agents and facilitator choose their own room actions', 403)
                result = store.conversation_action(member_id, payload)
                affected=result.pop('affected_members')
                self.server.capture_conversations(affected)
                if self.server.event: self.server.event.notify_action(payload,result,affected)
                return self.respond(result, 201)
            if len(parts) == 4 and parts[:2] == ["api", "problems"] and parts[3] == "comments" and method == "POST":
                result = store.comment(member_id, parts[2], payload)
                self.server.local_memory_after_write(member_id)
                return self.respond(result, 201)
            if len(parts) == 3 and parts[:2] == ["api", "problems"] and method == "PATCH":
                store.resolve(member_id, parts[2], payload.get("status"))
                return self.respond({"ok": True})
            if method == "POST" and path == "/api/messages":
                result = store.message(member_id, payload)
                self.server.local_memory_after_write(member_id)
                return self.respond(result, 201)
            if method == "POST" and path == "/api/assistant":
                self.server.rate_limit(("hermes", member_id), maximum=10)
                turn_id = store.begin_turn(member_id, payload.get("message"))
                try:
                    reply = self.server.hermes.chat(store, member_id, turn_id)
                    store.finish_turn(turn_id, reply=reply)
                    self.server.local_memory_after_write(member_id)
                except Exception as exc:
                    error = str(exc) if isinstance(exc, AppError) else "Hermes request failed unexpectedly; no automatic retry was made."
                    store.finish_turn(turn_id, error=error)
                    if isinstance(exc, AppError):
                        raise
                    raise AppError(error, 502) from None
                return self.respond({"id": turn_id, "reply": reply})
            raise AppError("Not found", 404)
        except AppError as exc:
            self.respond({"error": str(exc)}, exc.status)
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception:
            logging.exception("Residency request failed")
            self.respond({"error": "An internal error occurred"}, 500)

    do_GET = do_POST = do_PATCH = do_HEAD = do_PUT = do_DELETE = do_OPTIONS = handle_request


def main():
    parser = argparse.ArgumentParser(description="Independent Hermes residency app")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=7340)
    args = parser.parse_args()
    try:
        settings = Settings.from_env()
        if args.host not in ("127.0.0.1", "localhost", "::1") and (
                not settings.secure_cookies or not settings.public_origin.startswith("https://")):
            parser.error("Non-loopback binding requires HTTPS origin and secure cookies behind a reverse proxy")
        server = ResidencyServer((args.host, args.port), settings)
    except (ValueError, OSError) as exc:
        parser.error(str(exc))
    signal.signal(signal.SIGTERM, lambda *_: threading.Thread(target=server.shutdown, daemon=True).start())
    print(f"Residency: {settings.public_origin} · data: {settings.data_dir}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
