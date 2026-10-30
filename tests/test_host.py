import importlib.util
import os
from pathlib import Path
import stat
import sys
import tempfile
import unittest
from unittest.mock import patch

from residency.config import APP_ROOT

SCRIPTS = APP_ROOT / "scripts"


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


launcher = load("residency_hermes_launcher", SCRIPTS / "hermes.py")
with patch.dict(sys.modules, {"hermes": launcher}):
    host = load("residency_host", SCRIPTS / "host.py")


class HostTests(unittest.TestCase):
    def setUp(self):
        (APP_ROOT / ".data").mkdir(exist_ok=True)
        self.directory = tempfile.TemporaryDirectory(prefix="host-test-", dir=APP_ROOT / ".data")
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)

    def test_launcher_does_not_inherit_other_apps_credentials_or_profiles(self):
        with patch.dict(os.environ, {"OPENAI_API_KEY": "private-other-app-key", "HERMES_PROFILE": "personal",
                                    "PYTHONPATH": "/other-app", "HERMES_HOME": "/other-home"}):
            env = launcher.environment()
        for key in ("OPENAI_API_KEY", "HERMES_PROFILE", "PYTHONPATH"):
            self.assertNotIn(key, env)
        self.assertTrue(Path(env["HERMES_HOME"]).is_relative_to(APP_ROOT))
        self.assertTrue(Path(env["HERMES_SHARED_AUTH_DIR"]).is_relative_to(APP_ROOT))
        self.assertTrue(Path(env["UV_CACHE_DIR"]).is_relative_to(APP_ROOT))

    def test_env_file_roundtrip_and_private_permissions(self):
        path = self.root / ".env"
        values = {"HERMES_API_KEY": "test-secret", "RESIDENCY_JOIN_CODE": "test-invite"}
        host.write_env(path, values)
        self.assertEqual(host.read_env(path), values)
        self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)

    def test_environment_parser_does_not_execute_shell_content(self):
        path = self.root / ".env"
        path.write_text('# comments\nVALUE="$(touch sentinel)"\nEMPTY=\n')
        self.assertEqual(host.read_env(path)["VALUE"], "$(touch sentinel)")
        self.assertFalse((self.root / "sentinel").exists())
        path.write_text("not an assignment\n")
        with self.assertRaises(ValueError):
            host.read_env(path)

    def test_reinitializing_preserves_existing_secrets(self):
        values = {"HERMES_API_KEY": "existing-server-secret", "RESIDENCY_JOIN_CODE": "existing-invitation"}
        host.write_env(self.root / ".env", values)
        with patch.object(host, "ROOT", self.root), patch.object(host, "configure"):
            host.initialize()
        updated = host.read_env(self.root / ".env")
        self.assertEqual(updated["HERMES_API_KEY"], values["HERMES_API_KEY"])
        self.assertEqual(updated["RESIDENCY_JOIN_CODE"], values["RESIDENCY_JOIN_CODE"])
        self.assertEqual(host.read_env(self.root / ".hermes" / ".env")["API_SERVER_KEY"], values["HERMES_API_KEY"])

    def test_stop_refuses_stale_pid_belonging_to_another_process(self):
        import json
        (self.root / ".data").mkdir()
        (self.root / ".data" / "host-processes.json").write_text(json.dumps({"supervisor": os.getpid()}))
        with patch.object(host, "ROOT", self.root), patch.object(host.os, "kill") as kill:
            with self.assertRaises(SystemExit):
                host.stop()
        kill.assert_not_called()

    def test_missing_runtime_fails_with_setup_guidance(self):
        with patch.object(launcher, "ROOT", self.root):
            with self.assertRaises(SystemExit):
                launcher.interpreter()
