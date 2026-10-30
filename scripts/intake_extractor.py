"""Manage Zugrama's outbound CV extraction worker, separately from simulations."""
import argparse
import json
import os
from pathlib import Path
import secrets
import signal
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT/'scripts'))
from identity_test import private_json
from runtime_settings import gateway_settings
from residency.hermes import Hermes
from residency.intake_extractor import IntakeClient, IntakeExtractor
import hermes

DATA = ROOT/'.data'/'intake-extractor'
ORIGIN = 'https://zugrama-agent-residency.smudge0110.chatgpt.site'


def setup():
    DATA.mkdir(parents=True, exist_ok=True, mode=0o700)
    DATA.chmod(0o700)
    config = DATA/'config.json'
    if not config.exists():
        private_json(config, {'origin': ORIGIN, 'token': secrets.token_urlsafe(32), 'daily_limit': 50})
    return {'configured': True, 'config': str(config), 'model': 'gpt-5.6-terra'}


def running_pid():
    try:
        saved = json.loads((DATA/'process.json').read_text())
        args = (Path('/proc')/str(saved['pid'])/'cmdline').read_bytes().split(b'\0')
        return saved['pid'] if str(Path(__file__).resolve()).encode() in args and b'run' in args else None
    except (OSError, ValueError, KeyError):
        return None


def run():
    private_json(DATA/'process.json', {'pid':os.getpid()})
    config = json.loads((DATA/'config.json').read_text())
    os.umask(0o077)
    worker = IntakeExtractor(IntakeClient(config['origin'], config['token']), Hermes(gateway_settings(DATA,'intake-extraction-only-no-signups')), DATA/'attempts.sqlite3', config['daily_limit'])
    stopping = False
    def stop(*_):
        nonlocal stopping
        stopping = True
    signal.signal(signal.SIGTERM, stop)
    print('Zugrama CV worker started; GPT Terra, no event execution.', flush=True)
    while not stopping:
        try:
            outcome = worker.step()
            if outcome != 'idle': print('CV job '+outcome, flush=True)
        except Exception:
            # Never print HTTP bodies/headers, private keys, CVs or model replies.
            print('Site temporarily unavailable; polling will resume. No model retry.', flush=True)
        for _ in range(10):
            if stopping: break
            time.sleep(1)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('setup','run','start','status','stop'))
    args = parser.parse_args()
    try:
        if args.command == 'setup': result = setup()
        elif args.command == 'run': return run()
        elif args.command == 'start':
            if running_pid(): raise ValueError('The intake worker is already running')
            config = json.loads((DATA/'config.json').read_text())
            gateway_settings(DATA,'intake-extraction-only-no-signups')
            with (DATA/'worker.log').open('ab') as log:
                child = subprocess.Popen([sys.executable,'-B',str(Path(__file__).resolve()),'run'], cwd=ROOT, env=hermes.environment(), stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
            private_json(DATA/'process.json', {'pid': child.pid})
            time.sleep(1)
            if child.poll() is not None: raise ValueError('The intake worker could not start; inspect its private worker.log')
            result = {'running': True, 'origin': config['origin'], 'model': 'gpt-5.6-terra'}
        elif args.command == 'stop':
            pid = running_pid()
            if not pid: raise ValueError('No verified intake worker process is running; nothing was signalled')
            os.kill(pid, signal.SIGTERM)
            result = {'status': 'shutdown_requested'}
        else: result = {'running': bool(running_pid()), 'data': str(DATA), 'model': 'gpt-5.6-terra'}
    except (OSError, ValueError) as exc:
        parser.exit(1, str(exc)+'\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__': main()
