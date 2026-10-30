import sqlite3
import time
import unittest
from pathlib import Path

from residency.config import APP_ROOT, Settings
from residency.store import AppError, Store, digest
from tests.support import account, settings


class StoreTests(unittest.TestCase):
    def setUp(self):
        (APP_ROOT / ".data").mkdir(exist_ok=True)
        self.context = settings()
        self.config = self.context.__enter__()
        self.addCleanup(self.context.__exit__, None, None, None)
        self.store = Store(self.config)

    def join(self, email="ada@example.test", name="Ada"):
        token, csrf = self.store.register(account(email, name))
        return self.store.authenticate(token)["member_id"], token, csrf

    def test_join_login_password_hashing_and_logout(self):
        member, token, csrf = self.join()
        with self.store.db() as db:
            row = dict(db.execute("SELECT * FROM members").fetchone())
            session = dict(db.execute("SELECT * FROM sessions").fetchone())
        self.assertNotEqual(row["password_hash"], account()["password"])
        self.assertEqual(session["token_hash"], digest(token))
        self.assertNotIn(token, str(session))
        self.assertTrue(csrf)
        new_token, _ = self.store.login(account())
        self.assertNotEqual(token, new_token)
        self.assertEqual(self.store.authenticate(new_token)["member_id"], member)
        self.store.logout(token)
        with self.assertRaises(AppError):
            self.store.authenticate(token)

    def test_wrong_invitation_and_invalid_profiles_rejected(self):
        for changes in ({"join_code": "wrong"}, {"email": "invalid"}, {"name": " "},
                        {"password": "short"}, {"bio": []}, {"seeking": "a" * 2001}):
            with self.subTest(changes=changes), self.assertRaises(AppError):
                self.store.register({**account(), **changes})

    def test_duplicate_email_case_insensitive_and_invalid_credentials(self):
        self.join()
        with self.assertRaises(AppError) as error:
            self.store.register(account("ADA@EXAMPLE.TEST"))
        self.assertEqual(error.exception.status, 409)
        for payload in ({**account(), "password": "wrong"}, account("missing@example.test")):
            with self.assertRaises(AppError) as error:
                self.store.login(payload)
            self.assertEqual(error.exception.status, 401)

    def test_session_expiry(self):
        _, token, _ = self.join()
        with self.store.db() as db:
            db.execute("UPDATE sessions SET expires_at=?", (time.time() - 1,))
        with self.assertRaises(AppError):
            self.store.authenticate(token)

    def test_directory_omits_credentials_and_other_members_emails(self):
        ada, _, _ = self.join()
        bob, _, _ = self.join("bob@example.test", "Bob")
        snapshot = self.store.snapshot(ada)
        self.assertEqual(snapshot["me"]["email"], "ada@example.test")
        self.assertEqual(len(snapshot["members"]), 2)
        self.assertNotIn("bob@example.test", str(snapshot))
        self.assertNotIn("password", str(snapshot))
        self.assertNotIn("salt", str(snapshot))
        self.store.update_profile(bob, dict(name="Bobby", bio="Builder", seeking="Peers", offering="Code"))
        self.assertEqual(self.store.snapshot(ada)["members"][1]["name"], "Bobby")

    def test_dm_and_assistant_isolation_between_three_members(self):
        ada, _, _ = self.join()
        bob, _, _ = self.join("bob@example.test", "Bob")
        eve, _, _ = self.join("eve@example.test", "Eve")
        self.store.message(ada, dict(recipient_id=bob, body="Private DM"))
        turn = self.store.begin_turn(ada, "Private assistant question")
        self.store.finish_turn(turn, reply="Private assistant reply")
        self.assertEqual(len(self.store.snapshot(ada)["messages"]), 1)
        self.assertEqual(len(self.store.snapshot(bob)["messages"]), 1)
        self.assertEqual(self.store.snapshot(eve)["messages"], [])
        self.assertEqual(self.store.snapshot(bob)["assistant_turns"], [])
        self.assertEqual(self.store.snapshot(eve)["assistant_turns"], [])

    def test_shared_problem_comments_and_author_only_status(self):
        ada, _, _ = self.join()
        bob, _, _ = self.join("bob@example.test", "Bob")
        problem = self.store.problem(ada, dict(title="An experiment", body="How do I test this?"))
        self.store.comment(bob, problem["id"], dict(body="Try a baseline first."))
        with self.assertRaises(AppError) as error:
            self.store.resolve(bob, problem["id"], "solved")
        self.assertEqual(error.exception.status, 403)
        self.store.resolve(ada, problem["id"], "solved")
        snapshot = self.store.snapshot(bob)
        self.assertEqual(snapshot["problems"][0]["status"], "solved")
        self.assertEqual(snapshot["comments"][0]["body"], "Try a baseline first.")
        self.store.resolve(ada, problem["id"], "open")
        with self.assertRaises(AppError):
            self.store.resolve(ada, problem["id"], "anything")

    def test_invalid_targets_and_empty_messages(self):
        ada, _, _ = self.join()
        for recipient in (ada, "missing"):
            with self.assertRaises(AppError):
                self.store.message(ada, dict(recipient_id=recipient, body="hello"))
        with self.assertRaises(AppError):
            self.store.problem(ada, dict(title="", body="x"))
        with self.assertRaises(AppError):
            self.store.comment(ada, "missing", dict(body="hello"))
        with self.assertRaises(AppError):
            self.store.begin_turn(ada, [])

    def test_pending_turn_is_serialized_and_failure_does_not_block_future_work(self):
        ada, _, _ = self.join()
        turn = self.store.begin_turn(ada, "Question")
        with self.assertRaises(AppError) as error:
            self.store.begin_turn(ada, "Second question")
        self.assertEqual(error.exception.status, 409)
        self.store.finish_turn(turn, error="Unavailable")
        next_turn = self.store.begin_turn(ada, "Try again deliberately")
        self.store.finish_turn(next_turn, reply="Answer")
        self.assertEqual([t["status"] for t in self.store.snapshot(ada)["assistant_turns"]], ["failed", "completed"])

    def test_restart_preserves_state_and_marks_interrupted_turn(self):
        ada, token, _ = self.join()
        self.store.begin_turn(ada, "Interrupted")
        new_store = Store(self.config)
        self.assertEqual(new_store.instance_id, self.store.instance_id)
        self.assertEqual(new_store.authenticate(token)["member_id"], ada)
        self.assertEqual(new_store.snapshot(ada)["assistant_turns"][0]["status"], "failed")


class ConfigTests(unittest.TestCase):
    def test_reject_data_locations_outside_new_app(self):
        for path in (APP_ROOT.parent, APP_ROOT, APP_ROOT.parent / "environments" / "network-nine", Path("/tmp/data")):
            with self.subTest(path=path), self.assertRaises(ValueError):
                Settings(data_dir=path, join_code="test-invitation")

    def test_reject_bad_urls_and_missing_join_code(self):
        with self.assertRaises(ValueError):
            Settings()
        for url in ("file:///tmp/x", "http://user:pass@localhost", "http://localhost/?key=x"):
            with self.subTest(url=url), self.assertRaises(ValueError):
                Settings(join_code="test-invitation", hermes_url=url)

    def test_https_requires_secure_cookies(self):
        with self.assertRaises(ValueError):
            Settings(join_code="test-invitation", public_origin="https://residency.example")

    def test_timeout_must_be_finite_and_positive(self):
        for timeout in (-1, 0, float("nan"), float("inf"), 601):
            with self.subTest(timeout=timeout), self.assertRaises(ValueError):
                Settings(join_code="test-invitation", hermes_timeout=timeout)
