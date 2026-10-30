from contextlib import contextmanager
from dataclasses import replace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import tempfile
import threading

from residency.config import APP_ROOT, Settings
from residency.server import ResidencyServer

JOIN_CODE = "test-residency-invitation"


def account(email="ada@example.test", name="Ada"):
    return dict(name=name, email=email, password="a long test password", join_code=JOIN_CODE,
                bio="Researcher", seeking="Experiments", offering="Statistics")


@contextmanager
def settings(**overrides):
    with tempfile.TemporaryDirectory(prefix="test-", dir=APP_ROOT / ".data") as directory:
        from pathlib import Path
        yield Settings(data_dir=Path(directory), join_code=JOIN_CODE, **overrides)


class Gateway(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self):
        super().__init__(("127.0.0.1", 0), GatewayHandler)
        self.records = []
        self.models = [{'id':'hermes-agent','root':'hermes-agent'}]
        self.failure = None
        self.toolsets = [{"name": "terminal", "enabled": False, "tools": ["terminal"]}]
        self.finish = "stop"
        self.reply = "Talk with another resident about a small, testable next step."
        self.reply_factory = None
        self.delay = 0
        self.usage = None
        self.budget_guard = None
        self.entered = threading.Event()
        self.release = threading.Event()
        self.block = False
        self.url = f"http://127.0.0.1:{self.server_port}"


class GatewayHandler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def do_GET(self):
        if self.path == '/health':
            return self.respond({'status':'ok','residency_budget_guard':self.server.budget_guard})
        self.respond({"data": self.server.toolsets} if self.path == "/v1/toolsets" else {"data": self.server.models})

    def do_POST(self):
        import time
        payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        self.server.records.append({"path": self.path, "headers": dict(self.headers), "payload": payload})
        self.server.entered.set()
        if self.server.block:
            self.server.release.wait(5)
        time.sleep(self.server.delay)
        reply=self.server.reply_factory(payload) if self.server.reply_factory else self.server.reply
        self.respond({"choices": [{"message": {"content": reply}, "finish_reason": self.server.finish}],**({'usage':self.server.usage} if self.server.usage else {})})

    def respond(self, body):
        if self.server.failure == "malformed":
            raw, status = b"not json", 200
        elif isinstance(self.server.failure, int):
            raw, status = b'{"error":"secret-upstream-diagnostic"}', self.server.failure
        else:
            raw, status = json.dumps(body).encode(), 200
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        try:
            self.wfile.write(raw)
        except BrokenPipeError:
            pass


@contextmanager
def gateway():
    server = Gateway()
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.release.set()
        server.shutdown()
        server.server_close()
        thread.join(2)


@contextmanager
def app(config):
    # Bind first, then set the exact public origin before accepting requests.
    server = ResidencyServer(("127.0.0.1", 0), config)
    server.settings = replace(config, public_origin=f"http://127.0.0.1:{server.server_port}")
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()
        thread.join(2)
