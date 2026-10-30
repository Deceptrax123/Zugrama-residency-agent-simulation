"""Arm one event's retrospective without touching its running networking loop."""
import argparse
import fcntl
import http.cookiejar
import json
import os
from pathlib import Path
import sys
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT/'scripts')]
from residency.end_questionnaire import QuestionnaireRunner, ready, MODEL
from residency.hermes import Hermes, NoRedirect
from residency.markdown_memory import write_private
from runtime_settings import gateway_settings

DATA = ROOT/'.data/live-residency'
BASE = 'http://127.0.0.1:7380'


class HostReader:
    def __init__(self):
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}),
            urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()), NoRedirect())
        credentials = json.loads((ROOT/'.data/participant-launch/host-account.json').read_text())
        self.request('/api/login', {'email': credentials['email'], 'password': credentials['password']})

    def request(self, path, body=None):
        req = urllib.request.Request(BASE+path, data=json.dumps(body).encode() if body is not None else None,
            headers={'Origin': BASE, 'Content-Type': 'application/json'})
        with self.opener.open(req, timeout=30) as response:
            return json.load(response)

    def host_stopped_since(self, armed_at):
        cfg = json.loads((ROOT/'.data/participant-launch/hosted-access.json').read_text())
        req = urllib.request.Request(cfg['origin'].rstrip('/')+'/api/residency',
            headers={'Authorization': 'Bearer '+cfg['host_token'], 'User-Agent': 'Zugrama-End-Questionnaire/1.0'})
        with urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect()).open(req, timeout=30) as response:
            data = json.load(response)
        return any(c['kind'] == 'stop' and c['status'] == 'completed' and c['created_at'] > armed_at*1000
                   for c in data.get('commands', []))


def _watch_locked(event_id):
    os.umask(0o077)
    directory = DATA/'state/questionnaires'/event_id
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    path = directory/'status.json'
    state_path = DATA/'state/host-event/state.json'
    state = json.loads(state_path.read_text())
    if state.get('event_id') != event_id:
        raise ValueError('Current event does not match; nothing armed')
    saved = json.loads(path.read_text()) if path.exists() else None
    if saved and saved['status'] != 'armed':
        print(json.dumps({'status': saved['status'], 'message': 'Existing job not replayed.'}), flush=True)
        return
    job = saved or {'event_id': event_id, 'armed_at': time.time(), 'status': 'armed',
                    'model': MODEL, 'completed': [], 'observed_host_stop': False,
                    'networking_started_by_questionnaire': False, 'budget_usd': 5}
    write_private(path, json.dumps(job, indent=2))
    print(json.dumps({'status': 'armed', 'event_id': event_id, 'model': MODEL, 'model_calls': 0}), flush=True)
    host = HostReader()
    setup = json.loads((DATA/'setup.json').read_text())
    if setup.get('network_model', MODEL) != MODEL:
        raise ValueError('Configured networking model changed; no questionnaire model fallback')
    gateway = Hermes(gateway_settings(DATA/'state', setup['join_code'], model=MODEL))
    runner = QuestionnaireRunner(DATA, gateway)
    runner.initialize()
    while True:
        try:
            state = json.loads(state_path.read_text())
            if state.get('event_id') != event_id:
                job.update(status='cancelled_event_changed')
                break
            if state['status'] == 'stopping':
                job['observed_host_stop'] = True
                write_private(path, json.dumps(job, indent=2))
            if state['status'] in ('stopped', 'completed_with_errors', 'paused_quota'):
                # A process shutdown may also enter "stopping". Only the
                # authenticated hosted Stop command grants this dispatch.
                stopped_by_host = host.host_stopped_since(job['armed_at'])
                event = host.request('/api/event')
                if event.get('event_id') == event_id and ready(event, host_stop=stopped_by_host):
                    break
        except (OSError, ValueError):
            # Disconnection never grants permission to dispatch. Remain armed.
            pass
        time.sleep(5)
    if job['status'].startswith('cancelled'):
        write_private(path, json.dumps(job, indent=2))
        return
    job.update(status='answering', observed_host_stop=True, stopped_at=time.time())
    write_private(path, json.dumps(job, indent=2))
    def still_stopped():
        event = host.request('/api/event')
        return event.get('event_id') == event_id and ready(event, host_stop=True)
    try:
        for owner in state['starting_identities']:
            status = runner.run_owner(state, owner, still_stopped)
            if status == 'completed':
                job['completed'].append(owner)
            elif status in ('paused_quota', 'paused_budget', 'waiting_for_stop'):
                job.update(status=status)
                break
            else:
                job.setdefault('needs_review', {})[owner] = status
            write_private(path, json.dumps(job, indent=2))
        else:
            job['status'] = 'completed_with_errors' if job.get('needs_review') else 'completed'
    except Exception:
        job['status'] = 'failed_no_retry'
    write_private(path, json.dumps(job, indent=2))
    print(json.dumps({'status': job['status'], 'completed': len(job['completed']), 'total': len(state['starting_identities'])}), flush=True)


def watch(event_id):
    os.umask(0o077)
    directory = DATA/'state/questionnaires'/event_id
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (directory/'worker.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return _watch_locked(event_id)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('event_id', help='Existing event to arm; never starts or resumes networking')
    args = parser.parse_args()
    watch(args.event_id)
