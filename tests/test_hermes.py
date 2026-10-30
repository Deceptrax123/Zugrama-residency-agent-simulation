from dataclasses import replace
import json
import unittest
from unittest.mock import patch

from residency.config import APP_ROOT
from residency.hermes import Hermes
from residency.store import AppError, Store
from tests.support import account, gateway, settings


class HermesTests(unittest.TestCase):
    def setUp(self):
        (APP_ROOT / ".data").mkdir(exist_ok=True)
        self.gateway_context = gateway()
        self.gateway = self.gateway_context.__enter__()
        self.addCleanup(self.gateway_context.__exit__, None, None, None)
        self.context = settings(hermes_url=self.gateway.url, hermes_key="test-server-secret")
        self.config = self.context.__enter__()
        self.addCleanup(self.context.__exit__, None, None, None)
        self.store = Store(self.config)
        token, _ = self.store.register(account())
        self.member = self.store.authenticate(token)["member_id"]
        self.hermes = Hermes(self.config)

    def ask(self, message="Help with my experiment"):
        turn = self.store.begin_turn(self.member, message)
        try:
            reply = self.hermes.chat(self.store, self.member, turn)
            self.store.finish_turn(turn, reply=reply)
            return reply
        except Exception:
            self.store.finish_turn(turn, error="test failure")
            raise

    def test_real_http_contract_auth_model_history_and_unique_session(self):
        self.ask("First question")
        self.ask("Follow-up")
        request = self.gateway.records[-1]
        self.assertEqual(request["path"], "/v1/chat/completions")
        self.assertEqual(request["headers"]["Authorization"], "Bearer test-server-secret")
        headers = {k.lower(): v for k, v in request["headers"].items()}
        self.assertIn(self.member, headers["x-hermes-session-id"])
        self.assertIn(self.member, headers["x-hermes-session-key"])
        self.assertNotEqual(headers["idempotency-key"], {k.lower():v for k,v in self.gateway.records[0]["headers"].items()}["idempotency-key"])
        payload = request["payload"]
        self.assertEqual(payload["model"], "hermes-agent")
        self.assertFalse(payload["stream"])
        self.assertEqual([m["role"] for m in payload["messages"]], ["system", "user", "assistant", "user"])
        self.assertEqual(payload["messages"][-1]["content"], "Follow-up")

    def test_public_context_supplied_without_dms_or_other_private_turns(self):
        token, _ = self.store.register(account("bob@example.test", "Bob"))
        bob = self.store.authenticate(token)["member_id"]
        self.store.message(bob, dict(recipient_id=self.member, body="secret-direct-message"))
        t = self.store.begin_turn(bob, "secret-bob-question")
        self.store.finish_turn(t, reply="secret-bob-answer")
        self.store.problem(bob, dict(title="Public question", body="Public details"))
        self.ask()
        payload = json.dumps(self.gateway.records[-1]["payload"])
        self.assertIn("Public question", payload)
        for private in ("secret-direct-message", "secret-bob-question", "secret-bob-answer", "bob@example.test", "password_hash"):
            self.assertNotIn(private, payload)

    def test_terra_route_is_required_and_model_change_uses_a_fresh_session_scope(self):
        self.ask('First model')
        first = {k.lower():v for k,v in self.gateway.records[-1]['headers'].items()}
        self.hermes = Hermes(replace(self.config,hermes_model='gpt-5.6-terra'))
        with self.assertRaises(AppError):
            self.ask('Reject an unadvertised Terra route')
        self.assertEqual(len(self.gateway.records),1)
        self.gateway.models.append({'id':'gpt-5.6-terra','root':'gpt-5.6-terra'})
        self.ask('New model')
        last = {k.lower():v for k,v in self.gateway.records[-1]['headers'].items()}
        self.assertNotEqual(first['x-hermes-session-id'],last['x-hermes-session-id'])
        self.assertNotEqual(first['x-hermes-session-key'],last['x-hermes-session-key'])
        self.assertEqual(self.gateway.records[-1]['payload']['model'],'gpt-5.6-terra')
        self.assertIn('gpt-5.6-terra',self.hermes.health()['message'])

    def test_missing_key_fails_without_network(self):
        hermes = Hermes(replace(self.config, hermes_key=""))
        self.assertEqual(hermes.health()["status"], "unavailable")
        self.assertEqual(self.gateway.records, [])

    def test_shared_environment_is_supplied_and_reloaded_without_private_identity_fields(self):
        context = self.config.data_dir / "USER.md"
        context.write_text("Dhun setting. People may discuss anything; water is an optional topic.")
        with patch("residency.hermes.APP_ROOT", self.config.data_dir):
            self.ask("I would like to talk about music")
            system = self.gateway.records[-1]["payload"]["messages"][0]["content"]
            self.assertIn(context.read_text(), system)
            self.assertIn("optional possibilities, not assigned goals", system)
            context.write_text("Updated Dhun environment: the participants choose their own topics.")
            self.ask("Tell me more")
            system = self.gateway.records[-1]["payload"]["messages"][0]["content"]
            self.assertIn(context.read_text(), system)
            self.assertNotIn("water is an optional topic", system)

    def test_missing_environment_refuses_inference(self):
        with patch("residency.hermes.APP_ROOT", self.config.data_dir):
            with self.assertRaises(AppError) as error:
                self.ask()
        self.assertEqual(error.exception.status, 503)
        self.assertEqual(self.gateway.records, [])

    def test_enabled_tools_refuse_inference(self):
        self.gateway.toolsets[0]["enabled"] = True
        with self.assertRaises(AppError) as error:
            self.ask()
        self.assertEqual(error.exception.status, 503)
        self.assertEqual(self.gateway.records, [])

    def test_invalid_toolset_discovery_fails_closed(self):
        self.gateway.toolsets = [{}]
        self.assertEqual(self.hermes.health()["status"], "unavailable")

    def test_gateway_http_error_does_not_leak_diagnostics(self):
        for status in (401, 403, 429, 500):
            with self.subTest(status=status):
                self.gateway.failure = status
                health = self.hermes.health()
                self.assertEqual(health["status"], "unavailable")
                self.assertNotIn("secret-upstream-diagnostic", health["message"])
                self.assertNotIn("test-server-secret", health["message"])

    def test_malformed_json_reported(self):
        self.gateway.failure = "malformed"
        with self.assertRaises(AppError) as error:
            self.ask()
        self.assertEqual(error.exception.status, 502)

    def test_timeout_does_not_retry(self):
        self.hermes = Hermes(replace(self.config, hermes_timeout=.05))
        self.gateway.delay = .15
        with self.assertRaises(AppError) as error:
            self.ask()
        self.assertEqual(error.exception.status, 504)
        self.assertEqual(len(self.gateway.records), 1)

    def test_cancelled_and_error_responses_are_not_saved_as_success(self):
        for finish in ("error", "cancelled", None):
            with self.subTest(finish=finish), self.assertRaises(AppError):
                self.gateway.finish = finish
                self.ask()

    def test_iteration_limit_reply_is_marked_incomplete(self):
        self.gateway.finish = "length"
        self.assertIn("may be incomplete", self.ask())

    def test_empty_reply_rejected(self):
        self.gateway.reply = " "
        with self.assertRaises(AppError):
            self.ask()
