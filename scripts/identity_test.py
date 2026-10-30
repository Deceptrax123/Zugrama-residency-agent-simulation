"""Isolated identity test: sign up as host, author three agents, explicitly Start."""
import argparse
import json
import os
from pathlib import Path
import secrets
import signal
import subprocess
import sys
import threading
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT/'scripts'))
from residency.config import Settings
from residency.server import ResidencyServer
from residency.sandbox import IdentitySandbox
from host import read_env
import hermes

DATA = ROOT/'.data'/'identity-test'


def private_json(path, value):
    fd = os.open(path, os.O_WRONLY|os.O_CREAT|os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'w') as handle:
        json.dump(value, handle, indent=2)
    path.chmod(0o600)


def setup():
    DATA.mkdir(parents=True, exist_ok=True, mode=0o700)
    path = DATA/'setup.json'
    if not path.exists():
        private_json(path, {'kind': 'three-agent-identity-test', 'join_code': secrets.token_urlsafe(18)})
    result = json.loads(path.read_text())
    if result.get('kind') != 'three-agent-identity-test':
        raise ValueError('Existing test data is unrecognized and was preserved')
    return {**result, 'model_calls_on_setup': 0}


def settings(port):
    if not 1024 <= port <= 65535 or port in (7340,7350,8642):
        raise ValueError('Choose a separate loopback port; 7360 is the default')
    config = json.loads((DATA/'setup.json').read_text())
    if config.get('kind') != 'three-agent-identity-test':
        raise ValueError('Prepare this test with setup first')
    env = read_env(ROOT/'.env')
    if env.get('HERMES_MODEL') != 'gpt-5.6-terra':
        raise ValueError('Configure the isolated Hermes gateway for gpt-5.6-terra first')
    return Settings(data_dir=DATA/'state', join_code=config['join_code'],
        hermes_url=env.get('HERMES_API_URL','http://127.0.0.1:8642'),
        hermes_key=env.get('HERMES_API_KEY',''), hermes_model='gpt-5.6-terra',
        hermes_timeout=180, public_origin=f'http://127.0.0.1:{port}')


def running_pid():
    path = DATA/'process.json'
    if not path.exists(): return None
    saved = json.loads(path.read_text())
    try:
        args = (Path('/proc')/str(saved['pid'])/'cmdline').read_bytes().split(b'\0')
    except OSError:
        return None
    return saved['pid'] if str(Path(__file__).resolve()).encode() in args and b'run' in args else None


def run(port):
    config = settings(port)
    server = ResidencyServer(('127.0.0.1', port), config)
    server.sandbox = IdentitySandbox(server)
    from residency.local_mem0 import AgentMem0,SERVICE
    from residency.sleep_cycle import SleepCycle
    if SERVICE.is_file():
        server.semantic=AgentMem0(server)
        server.cycle=SleepCycle(server,server.semantic.client)
    signal.signal(signal.SIGTERM, lambda *_: threading.Thread(target=server.shutdown, daemon=True).start())
    print(f'Identity test frontend + backend: {config.public_origin} (idle until host Start)', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


def start(port):
    settings(port)
    if running_pid(): raise ValueError('The identity test is already running')
    with (DATA/'app.log').open('ab') as log:
        process = subprocess.Popen([sys.executable,'-B',str(Path(__file__).resolve()),'run','--port',str(port)],
            cwd=ROOT, env=hermes.environment(), stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
            start_new_session=True)
    time.sleep(1)
    if process.poll() is not None:
        raise ValueError('Identity test could not start; inspect .data/identity-test/app.log')
    private_json(DATA/'process.json', {'pid': process.pid, 'port': port})
    return {'status': 'running', 'url': f'http://127.0.0.1:{port}', 'event': 'idle'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('setup','start','run','status','stop'))
    parser.add_argument('--port', type=int, default=7360)
    args = parser.parse_args()
    try:
        if args.command == 'setup': result = setup()
        elif args.command == 'start': result = start(args.port)
        elif args.command == 'run': return run(args.port)
        elif args.command == 'stop':
            pid = running_pid()
            if not pid: raise ValueError('No verified identity-test process is running; nothing was signalled')
            os.kill(pid, signal.SIGTERM)
            result = {'status': 'shutdown_requested'}
        else: result = {'running': bool(running_pid()), 'data': str(DATA)}
    except (ValueError, OSError, KeyError) as exc:
        parser.exit(1, str(exc)+'\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__': main()
