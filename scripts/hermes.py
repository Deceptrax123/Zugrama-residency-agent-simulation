#!/usr/bin/env python3
"""Run the residency's isolated Hermes install without global launchers."""
import hashlib
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / ".tools" / "hermes-agent"


def environment():
    # Preserve host/TLS basics, without inheriting unrelated apps' API credentials.
    keep = {"PATH", "HOME", "USER", "LOGNAME", "LANG", "LC_ALL", "LC_CTYPE", "TZ", "TERM",
            "COLORTERM", "SSL_CERT_FILE", "SSL_CERT_DIR", "REQUESTS_CA_BUNDLE",
            "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY", "http_proxy",
            "https_proxy", "all_proxy", "no_proxy", "SSH_CONNECTION", "SSH_TTY"}
    env = {key: value for key, value in os.environ.items() if key in keep}
    env.update(
        HERMES_HOME=str(ROOT / ".hermes"),
        HERMES_RUNTIME_DIR=str(ROOT / ".tools" / "hermes-runtime"),
        HERMES_INSTALL_ROOT=str(SOURCE),
        HERMES_SHARED_AUTH_DIR=str(ROOT / ".hermes" / "shared"),
        UV_PYTHON_INSTALL_DIR=str(ROOT / ".tools" / "python"),
        UV_CACHE_DIR=str(ROOT / ".tools" / "uv-cache"),
        PYTHONDONTWRITEBYTECODE="1",
    )
    return env


def interpreter():
    key = hashlib.sha256(str(SOURCE.resolve()).encode()).hexdigest()[:16]
    facts = ROOT / ".hermes" / "installs" / key / "facts.json"
    try:
        data = json.loads(facts.read_text())
        python = Path(data["packages"]["venv"]["environment"]) / "bin" / "python"
    except (OSError, ValueError, KeyError) as exc:
        raise SystemExit("The isolated Hermes runtime is not installed. See README.md.") from exc
    if not python.is_file() or not python.resolve().is_relative_to(ROOT):
        raise SystemExit("Hermes runtime must live inside residency_app")
    return python


def main():
    python = interpreter()
    os.chdir(SOURCE)
    os.execve(str(python), [str(python), "-B", "-m", "hermes_cli.main", *sys.argv[1:]], environment())


if __name__ == "__main__":
    main()
