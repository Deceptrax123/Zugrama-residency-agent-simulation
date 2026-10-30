#!/usr/bin/env python3
"""Initialize/run the isolated local residency stack. Never installs system services."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import secrets
import signal
import subprocess
import sys
import time

import hermes

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def read_env(path):
    values = {}
    if path.exists():
        for line in path.read_text().splitlines():
            if line.strip() and not line.lstrip().startswith("#"):
                key, separator, value = line.partition("=")
                if not separator or not key.strip().replace("_", "").isalnum():
                    raise ValueError(f"Invalid environment assignment in {path}")
                values[key.strip()] = value.strip().strip("\"'")
    return values


def write_env(path, values):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    # Called only with generated secrets or existing validated assignments.
    content = "".join(f"{key}={value}\n" for key, value in values.items())
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as stream:
        stream.write(content)
    path.chmod(0o600)


def initialize():
    values = read_env(ROOT / ".env")
    defaults = {
        "RESIDENCY_JOIN_CODE": secrets.token_urlsafe(24),
        "RESIDENCY_ORIGIN": "http://127.0.0.1:7340",
        "RESIDENCY_SECURE_COOKIES": "false",
        "HERMES_API_URL": "http://127.0.0.1:8642",
        "HERMES_API_KEY": secrets.token_urlsafe(32),
        "HERMES_MODEL": "hermes-agent",
        "HERMES_TIMEOUT": "90",
    }
    for key, value in defaults.items():
        if not values.get(key):
            values[key] = value
    write_env(ROOT / ".env", values)
    gateway = read_env(ROOT / ".hermes" / ".env")
    gateway.update(API_SERVER_ENABLED="true", API_SERVER_HOST="127.0.0.1",
                   API_SERVER_PORT="8642", API_SERVER_KEY=values["HERMES_API_KEY"])
    write_env(ROOT / ".hermes" / ".env", gateway)
    configure()
    print("Prepared app and gateway configuration; secrets are in residency_app/.env (mode 600).")


def configure(provider=None, model=None, import_codex=False):
    if import_codex and provider != 'openai-codex':
        raise ValueError('Codex credential import requires --provider openai-codex')
    code = """
import json, sys
options = json.loads(sys.stdin.read())
sys.path.insert(0, options['root'])
from residency.gateway_config import configure_gateway
from hermes_cli.config import load_config, save_config
config = configure_gateway(load_config(), options['provider'], options['model'])
if options['import_codex']:
    from hermes_cli.auth_codex import _import_codex_cli_tokens, _save_codex_tokens
    tokens = _import_codex_cli_tokens()
    if not tokens:
        raise SystemExit('No valid linked Codex CLI credentials available. Sign in before importing.')
    _save_codex_tokens(tokens)
    print('Imported the linked account into the isolated Hermes auth store; credentials were not displayed.')
save_config(config)
print('Configured dedicated Hermes gateway: provider=' + config['model']['provider'] + ', model=' + str(config['model'].get('default', 'provider default')) + '; native runtime, tools/global memory/fallbacks disabled.')
"""
    options = {'root': str(ROOT), 'provider': provider, 'model': model, 'import_codex': import_codex}
    subprocess.run([str(hermes.interpreter()), "-B", "-c", code], input=json.dumps(options), text=True,
                   env=hermes.environment(), cwd=hermes.SOURCE, check=True)
    if model is not None:
        values = read_env(ROOT / '.env')
        values['HERMES_MODEL'] = model
        write_env(ROOT / '.env', values)


def status():
    from residency.config import Settings
    from residency.hermes import Hermes
    env = read_env(ROOT / ".env")
    config = Settings(join_code=env.get("RESIDENCY_JOIN_CODE", ""),
                      hermes_url=env.get("HERMES_API_URL", "http://127.0.0.1:8642"),
                      hermes_key=env.get("HERMES_API_KEY", ""),
                      hermes_model=env.get('HERMES_MODEL','hermes-agent'))
    print(json.dumps({"app_origin": env.get("RESIDENCY_ORIGIN"), "hermes": Hermes(config).health()}, indent=2))


def live_test():
    env = {**hermes.environment(), **read_env(ROOT / ".env"), "RESIDENCY_LIVE_HERMES": "1"}
    result = subprocess.run([sys.executable, "-B", "-m", "unittest", "tests.test_live", "-v"], cwd=ROOT, env=env)
    raise SystemExit(result.returncode)


def run():
    values = read_env(ROOT / ".env")
    if not values:
        raise SystemExit("Run python3 -B scripts/host.py init first")
    data = ROOT / ".data"
    data.mkdir(exist_ok=True, mode=0o700)
    with (data / "host.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise SystemExit("The residency host supervisor is already running") from None
        from urllib.parse import urlsplit
        import socket
        # Refuse to adopt or interfere with an existing process on either port.
        ports = [urlsplit(values['RESIDENCY_ORIGIN']).port or 7340,
                 urlsplit(values['HERMES_API_URL']).port or 8642]
        for port in ports:
            with socket.socket() as probe:
                try:
                    probe.bind(("127.0.0.1", port))
                except OSError:
                    raise SystemExit(f"Port {port} is already occupied; no service was started") from None
        children = []

        def stop(*_):
            for child in children:
                if child.poll() is None:
                    child.terminate()

        signal.signal(signal.SIGTERM, stop)
        signal.signal(signal.SIGINT, stop)
        gateway_env = hermes.environment()
        gateway_env.update(API_SERVER_ENABLED="true", API_SERVER_HOST="127.0.0.1",
                           API_SERVER_PORT=str(ports[1]), API_SERVER_KEY=values['HERMES_API_KEY'])
        try:
            with (data / "gateway.log").open("ab") as gateway_log, (data / "app.log").open("ab") as app_log:
                children.append(subprocess.Popen([str(hermes.interpreter()), "-B", str(ROOT/'scripts/gateway_runtime.py')],
                    cwd=hermes.SOURCE, env=gateway_env, stdout=gateway_log, stderr=subprocess.STDOUT))
                app_env = {**hermes.environment(), **values}
                children.append(subprocess.Popen([sys.executable, "-B", "-m", "residency.server", "--port", str(ports[0])],
                    cwd=ROOT, env=app_env, stdout=app_log, stderr=subprocess.STDOUT))
                (data / "host-processes.json").write_text(json.dumps({"supervisor": os.getpid(), "gateway": children[0].pid, "app": children[1].pid}))
                print(f"Residency supervisor running at {values['RESIDENCY_ORIGIN']}; logs in .data/", flush=True)
                while all(child.poll() is None for child in children):
                    time.sleep(.5)
                failed = [child.returncode for child in children if child.poll() is not None]
                if any(code != 0 for code in failed):
                    raise SystemExit("A residency service exited; see .data/app.log and .data/gateway.log")
        finally:
            stop()
            for child in children:
                try:
                    child.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.wait()


def start():
    data = ROOT / ".data"
    data.mkdir(exist_ok=True, mode=0o700)
    with (data / "host.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise SystemExit("The residency supervisor is already running") from None
    with (data / "supervisor.log").open("ab") as log:
        child = subprocess.Popen([sys.executable, "-B", str(Path(__file__).resolve()), "run"],
            cwd=ROOT, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
            start_new_session=True)
    time.sleep(1)
    if child.poll() is not None:
        raise SystemExit("The supervisor could not start; see .data/supervisor.log")
    print(f"Started isolated residency supervisor (PID {child.pid}).")


def stop():
    path = ROOT / ".data" / "host-processes.json"
    if not path.exists():
        raise SystemExit("No residency supervisor record found")
    pid = json.loads(path.read_text())["supervisor"]
    try:
        arguments = (Path('/proc') / str(pid) / 'cmdline').read_bytes().split(b'\0')
    except OSError:
        raise SystemExit("The recorded residency supervisor is no longer running") from None
    expected = str(Path(__file__).resolve()).encode()
    if expected not in arguments or b'run' not in arguments:
        raise SystemExit("PID no longer belongs to this residency supervisor; refusing to signal it")
    os.kill(pid, signal.SIGTERM)
    print("Requested shutdown of this residency supervisor and its two services.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("init", "configure", "start", "stop", "run", "status", "live-test"))
    parser.add_argument('--provider', choices=('nous', 'openai-codex'))
    parser.add_argument('--model')
    parser.add_argument('--import-codex', action='store_true')
    args = parser.parse_args()
    if args.command == 'configure':
        configure(args.provider, args.model, args.import_codex)
        return
    if args.provider or args.model or args.import_codex:
        parser.error('Provider/model/import options apply only to configure')
    {"init": initialize, "configure": configure, "start": start, "stop": stop,
     "run": run, "status": status, "live-test": live_test}[args.command]()


if __name__ == "__main__":
    main()
