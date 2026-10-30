"""Opt-in real gateway smoke test. Never masquerades as a contract test."""
import os
import unittest

from residency.config import APP_ROOT, Settings
from residency.hermes import Hermes
from residency.store import Store
from tests.support import account, app, settings


@unittest.skipUnless(os.environ.get("RESIDENCY_LIVE_HERMES") == "1", "Set RESIDENCY_LIVE_HERMES=1 to call a configured real Hermes gateway")
class LiveHermesTests(unittest.TestCase):
    def test_live_completion(self):
        config = Settings.from_env()
        (APP_ROOT / ".data").mkdir(exist_ok=True)
        with settings(hermes_url=config.hermes_url, hermes_key=config.hermes_key,
                      hermes_model=config.hermes_model) as isolated:
            store = Store(isolated)
            token, _ = store.register(account())
            member = store.authenticate(token)["member_id"]
            turn = store.begin_turn(member, "Reply with exactly this sentence: Residency connection verified.")
            reply = Hermes(isolated).chat(store, member, turn)
            self.assertIn("Residency connection verified", reply)

    def test_live_app_account_and_assistant_http_path(self):
        from tests.test_integration import Client
        config = Settings.from_env()
        (APP_ROOT / ".data").mkdir(exist_ok=True)
        with settings(hermes_url=config.hermes_url, hermes_key=config.hermes_key,
                      hermes_model=config.hermes_model) as isolated, app(isolated) as server:
            client = Client(f"http://127.0.0.1:{server.server_port}")
            client.join("live-http@example.test", "Synthetic live-test resident")
            status, result, _ = client.request("/api/assistant", "POST", {
                "message": "Reply with exactly this sentence: Residency HTTP path verified."})
            self.assertEqual(status, 200, result)
            self.assertIn("Residency HTTP path verified", result["reply"])
            turns = client.request("/api/state")[1]["assistant_turns"]
            self.assertEqual(turns[0]["status"], "completed")
