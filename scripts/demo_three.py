"""Three fictional resident logins, with the real Hermes gateway.

Server launch is idle. Only the authenticated host's Start action creates event
workers and model calls; manual use remains available. No daily schedule is set.
"""
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
from residency.memory import ConversationMemory
from residency.server import ResidencyServer
from residency.store import Store
from host import read_env
import hermes

DATA = ROOT / '.data' / 'demo-three'
DEMO_PASSWORD = 'residency-demo-only-2026'
PERSONAS = (
    {'name':'Demo Asha', 'email':'asha@example.test',
     'bio':'Fictional test resident. Interested in sustainable water, music, and practical experimentation.',
     'offering':'Test persona: Python skills and simple data-analysis drafts.',
     'seeking':'Thoughtful discussion, useful disagreement, and collaborators on ideas.',
     'introduction':'I am Demo Asha, a fictional test resident. I enjoy music and practical experiments. I am skilled in Python data analysis. My priority is understanding useful ideas before making commitments.'},
    {'name':'Demo Kabir', 'email':'kabir@example.test',
     'bio':'Fictional test resident. Interested in agriculture, community design, and learning from different viewpoints.',
     'offering':'Test persona: system-design ideas, pseudocode, and constructive critique.',
     'seeking':'People with complementary interests and skills, and concrete questions to explore.',
     'introduction':'I am Demo Kabir, a fictional test resident. I enjoy agriculture and community design. I can help draft pseudocode. I disagree with scaling an idea before understanding its local constraints.'},
    {'name':'Demo Mira', 'email':'mira@example.test',
     'bio':'Fictional test resident. Interested in learning, art, interfaces, and open-ended conversations.',
     'offering':'Test persona: interface sketches, reflective questions, and documentation drafts.',
     'seeking':'Interesting people, new perspectives, and ideas worth discussing further.',
     'introduction':'I am Demo Mira, a fictional test resident. I enjoy art, learning, and thoughtful conversation. I am skilled in writing documentation. My main priority is getting to know people and discovering shared interests.'},
)


def private_json(path, value):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'w') as handle:
        json.dump(value, handle, indent=2)
        handle.write('\n')
    path.chmod(0o600)


def setup():
    if (DATA / 'demo.json').is_file():
        saved = json.loads((DATA / 'demo.json').read_text())
        if saved.get('kind') != 'manual-three-persona-demo' or saved.get('status') != 'ready':
            raise ValueError('Demo setup is incomplete or unrecognized; existing data was preserved.')
        return {'status':'ready', 'accounts_file':str(DATA/'accounts.json'), 'existing_data_preserved':True}
    DATA.mkdir(parents=True, mode=0o700)  # Never adopt an existing directory.
    config = {'kind':'manual-three-persona-demo', 'status':'preparing',
              'join_code':secrets.token_urlsafe(24), 'autonomous_agents':False}
    private_json(DATA/'demo.json',config)
    store = Store(Settings(data_dir=DATA/'state', join_code=config['join_code']))
    accounts = []
    for persona in PERSONAS:
        token, _ = store.register({**persona, 'join_code':config['join_code'], 'password':DEMO_PASSWORD})
        member = store.authenticate(token)['member_id']
        store.logout(token)
        store.introduce(member, {'body':persona['introduction']})
        accounts.append({'name':persona['name'],'email':persona['email'],
                         'password':DEMO_PASSWORD,'member_id':member})
    memory = ConversationMemory(store)
    for account in accounts:
        while memory.batch(account['member_id'], {'introduction'}):
            memory.capture_conversations(account['member_id'])
    private_json(DATA/'accounts.json',accounts)
    config['status'] = 'ready'
    private_json(DATA/'demo.json',config)
    return {'status':'ready','accounts_file':str(DATA/'accounts.json'),
            'personas':[a['name'] for a in accounts], 'model_calls':0, 'autonomous_agents':False}


def settings(port):
    if not 1024 <= port <= 65535 or port in (7340,8642):
        raise ValueError('Choose a separate loopback port from 1024–65535, excluding 7340/8642')
    demo = json.loads((DATA/'demo.json').read_text())
    if demo.get('kind') != 'manual-three-persona-demo' or demo.get('status') != 'ready':
        raise ValueError('Prepare the demo before launching it')
    env = read_env(ROOT/'.env')
    if env.get('HERMES_MODEL') != 'gpt-5.6-terra':
        raise ValueError('Configure the dedicated Hermes gateway for gpt-5.6-terra first')
    return Settings(data_dir=DATA/'state',join_code=demo['join_code'],
        hermes_url=env.get('HERMES_API_URL','http://127.0.0.1:8642'),
        hermes_key=env.get('HERMES_API_KEY',''),hermes_model='gpt-5.6-terra',
        hermes_timeout=180, public_origin=f'http://127.0.0.1:{port}')


def running_pid():
    path = DATA/'process.json'
    if not path.exists():
        return None
    saved = json.loads(path.read_text())
    pid = saved['pid']
    try:
        args=(Path('/proc')/str(pid)/'cmdline').read_bytes().split(b'\0')
    except OSError:
        return None
    if str(Path(__file__).resolve()).encode() not in args or b'run' not in args:
        return None
    return pid


def run(port):
    config = settings(port)
    server = ResidencyServer(('127.0.0.1',port),config)
    from residency.event import HostEvent
    accounts=json.loads((DATA/'accounts.json').read_text())
    profiles={account['member_id']:PERSONAS[index] for index,account in enumerate(accounts)}
    server.event=HostEvent(server,accounts[0]['member_id'],profiles,DATA/'host-event')
    signal.signal(signal.SIGTERM, lambda *_:threading.Thread(target=server.shutdown,daemon=True).start())
    print(f'Three-persona frontend and backend: {config.public_origin}',flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


def start(port):
    settings(port)
    if running_pid():
        raise ValueError('The manual three-persona demo is already running')
    with (DATA/'app.log').open('ab') as log:
        process = subprocess.Popen([sys.executable,'-B',str(Path(__file__).resolve()),'run','--port',str(port)],
            cwd=ROOT,env=hermes.environment(),stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,
            start_new_session=True)
    time.sleep(1)
    if process.poll() is not None:
        raise ValueError('Demo could not start. See .data/demo-three/app.log; no model calls were made.')
    private_json(DATA/'process.json',{'pid':process.pid,'port':port})
    return {'status':'running','url':f'http://127.0.0.1:{port}', 'pid':process.pid,
            'accounts_file':str(DATA/'accounts.json'), 'autonomous_agents':False}


def stop():
    pid = running_pid()
    if not pid:
        raise ValueError('No verified three-persona demo process is running; nothing was signalled')
    os.kill(pid,signal.SIGTERM)
    return {'status':'shutdown_requested'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=('setup','start','run','status','stop'))
    parser.add_argument('--port',type=int,default=7350)
    args = parser.parse_args()
    try:
        if args.command == 'setup': result=setup()
        elif args.command == 'start': result=start(args.port)
        elif args.command == 'run': return run(args.port)
        elif args.command == 'stop': result=stop()
        else: result={'running':bool(running_pid()),'accounts_file':str(DATA/'accounts.json')}
    except (ValueError,OSError,KeyError) as exc:
        parser.exit(1,str(exc)+'\n')
    print(json.dumps(result,indent=2))


if __name__ == '__main__':
    main()
