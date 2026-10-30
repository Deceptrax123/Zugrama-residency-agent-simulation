"""Separate live cohort server. Launch is idle; only host Start dispatches agents."""
import argparse
from dataclasses import replace
import json
import os
from pathlib import Path
import secrets
import signal
import subprocess
import sys
import threading
import time
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'scripts')]
from identity_test import private_json
from runtime_settings import gateway_settings
from residency.cohort import LiveCohort
from residency.cohort_capacity import MAX_RESIDENTS
from residency.server import ResidencyServer
from residency.local_mem0 import AgentMem0
from residency.sleep_cycle import SleepCycle
import hermes
DATA=ROOT/'.data/live-residency'
DEFAULT_NETWORK_MODEL='gpt-6.1-sol'


def setup():
    DATA.mkdir(parents=True,exist_ok=True,mode=0o700);DATA.chmod(0o700)
    target=DATA/'setup.json'
    if not target.exists():private_json(target,{'kind':'zugrama-live-cohort/v1','join_code':secrets.token_urlsafe(24),'agent_limit':MAX_RESIDENTS})
    data=json.loads(target.read_text())
    if data.get('kind')!='zugrama-live-cohort/v1':raise ValueError('Unrecognized data; it was preserved')
    return data


def config():
    saved=setup()
    return gateway_settings(DATA/'state',saved['join_code'],model=saved.get('network_model',DEFAULT_NETWORK_MODEL),reasoning_effort=saved.get('network_reasoning_effort'))


def pid():
    try:
        current=json.loads((DATA/'process.json').read_text())['pid']
        args=(Path('/proc')/str(current)/'cmdline').read_bytes().split(b'\0')
        return current if str(Path(__file__).resolve()).encode() in args and b'run' in args else None
    except (OSError,KeyError,ValueError):return None


def run():
    os.umask(0o077)
    server=ResidencyServer(('127.0.0.1',7380),config())
    private_json(DATA/'process.json',{'pid':os.getpid()})
    server.audit_directory=DATA/'audit';server.network_memory_enabled=True;server.bounded_context=True;server.resilient_events=True
    server.continue_existing_rooms=True
    server.delegate_enabled=setup().get('delegate_enabled',False)
    server.allowance_transfers_enabled=setup().get('allowance_transfers_enabled',False)
    server.event_additions=setup().get('event_additions',[])
    server.sandbox=LiveCohort(server,setup()['agent_limit'])
    server.semantic=AgentMem0(server);server.cycle=SleepCycle(server,server.semantic.client)
    from residency.agent_tools import AgentTools
    server.agent_tools=AgentTools(server)
    from residency.semantic_insights import SemanticInsights
    server.insight_analysis=SemanticInsights(server)
    bridge=None
    if (DATA/'site-bridge.json').exists():
        from residency.site_bridge import SiteBridge
        bridge=SiteBridge(server,DATA/'site-bridge.json');bridge.start()
    signal.signal(signal.SIGTERM,lambda *_:threading.Thread(target=server.shutdown,daemon=True).start())
    print('Zugrama host frontend/backend http://127.0.0.1:7380; event idle until host Start.',flush=True)
    try:server.serve_forever()
    finally:
        if bridge:bridge.close()
        server.server_close()


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('command',choices=('setup','start','run','status','stop'));args=parser.parse_args()
    if args.command=='run':return run()
    setup()
    if args.command=='setup':result={'configured':True,'model':config().hermes_model,'host_invitation_file':str(DATA/'setup.json'),'max_residents':setup()['agent_limit'],'model_calls':0}
    elif args.command=='start':
        if pid():raise SystemExit('Live residency is already running')
        with (DATA/'app.log').open('ab') as log:child=subprocess.Popen([sys.executable,'-B',str(Path(__file__).resolve()),'run'],cwd=ROOT,env=hermes.environment(),stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
        private_json(DATA/'process.json',{'pid':child.pid});time.sleep(1)
        if child.poll() is not None:raise SystemExit('Startup failed; inspect .data/live-residency/app.log')
        result={'running':True,'url':'http://127.0.0.1:7380','event_started':False}
    elif args.command=='stop':
        current=pid()
        if not current:raise SystemExit('No verified live server; no signal sent')
        os.kill(current,signal.SIGTERM);result={'status':'shutdown_requested'}
    else:result={'running':bool(pid()),'url':'http://127.0.0.1:7380','data':str(DATA),'model':config().hermes_model}
    print(json.dumps(result,indent=2))


if __name__=='__main__':main()
