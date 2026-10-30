"""Disposable signup-to-seven-nights test. --live permits 21 real Terra requests."""
import argparse
from contextlib import ExitStack
import json
from pathlib import Path
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'scripts'))
from residency.local_mem0 import AgentMem0, LocalMemoryClient
from residency.sandbox import IdentitySandbox
from residency.sleep_cycle import SleepCycle
from tests.support import app, gateway, settings
from tests.test_integration import Client
from tests.test_identity_sandbox import persona
from tests.test_local_memory import FakeMemory
from host import read_env


def check(client,path,method='GET',body=None):
    status,value,_=client.request(path,method,body)
    if status not in (200,201):raise RuntimeError(f'{method} {path}: {status}: {value}')
    return value


def run(live=False):
    started=time.perf_counter();report={'live':live,'days':7,'network_calls_limit':21,'checks':[]}
    with ExitStack() as stack:
        if live:
            env=read_env(ROOT/'.env')
            if env.get('HERMES_MODEL')!='gpt-5.6-terra':raise ValueError('The live test requires the explicit Terra route')
            client_memory=LocalMemoryClient();client_memory.health()
            config=stack.enter_context(settings(hermes_url=env['HERMES_API_URL'],hermes_key=env['HERMES_API_KEY'],hermes_model='gpt-5.6-terra',hermes_timeout=180))
        else:
            backend=stack.enter_context(gateway())
            backend.budget_guard='residency-usd-v1'
            backend.usage={'prompt_tokens':1000,'completion_tokens':100,'total_tokens':1100}
            def reply(payload):
                ctx=json.loads(payload['messages'][-1]['content'])
                joined=[room for room in ctx['conversations'] if room['joined']]
                action={'wait_seconds':3600,'start_conversations':[],'join_conversations':[],'messages':[],'leave_conversations':[]}
                if joined:action['messages']=[{'conversation_id':joined[0]['id'],'body':'I reconsider that assumption and enjoy exploring this idea.'}]
                else:action['start_conversations']=[{'with':next(p['id'] for p in ctx['directory'] if p['id']!=ctx['member_id']),'body':'I enjoy meeting people and exploring useful ideas.'}]
                return json.dumps(action)
            backend.reply_factory=reply;client_memory=FakeMemory()
            config=stack.enter_context(settings(hermes_url=backend.url,hermes_key='synthetic-only'))
        server=stack.enter_context(app(config))
        server.sandbox=IdentitySandbox(server)
        server.semantic=AgentMem0(server,client_memory)
        server.cycle=SleepCycle(server,client_memory)
        host=Client(server.settings.public_origin)
        host_id=host.join('week-host@example.test','Synthetic week host')
        report['checks'].append('Host signup and session')
        for slot,name in enumerate(('QA Asha','QA Kabir','QA Mira'),1):
            profile=persona(name)
            profile.update(moral_compass='I value care, fairness and honest uncertainty. I can reconsider my views after hearing evidence.',political_standing='',
                           nationality='',region='')
            check(host,'/api/sandbox/agents','POST',{'slot':slot,'identity':profile})
        state=check(host,'/api/state');assert state['event']['calls']==0
        for agent in state['sandbox']['agents']:
            check(host,'/api/agent-budget','POST',{'owner_id':agent['member_id'],'limit_usd':'10.00','reserve_usd':'1.90'})
        assert len(state['sandbox']['agents'])==3 and len(state['introductions'])==4
        report['checks'].append('Three complete identities, public introductions, private values and idle startup')
        report['checks'].append('Independent USD allowances and wrap-up reserves configured before Start')
        check(host,'/api/event/start','POST',{'max_calls':3,'npc_enabled':True,'seven_days':True})
        event_id=server.event.state['event_id']
        for day in range(1,8):
            deadline=time.monotonic()+300
            while server.event.active:
                if time.monotonic()>deadline:raise RuntimeError('Networking deadline exceeded')
                time.sleep(.1)
            if server.event.state['status']=='failed':raise RuntimeError(server.event.state['error'])
            for thread in server.event.threads:thread.join(3)
            check(host,'/api/day-cycle/sleep','POST',{})
            deadline=time.monotonic()+600
            while server.cycle.thread.is_alive():
                if time.monotonic()>deadline:raise RuntimeError('Bedtime deadline exceeded')
                time.sleep(.2)
            cycle=check(host,'/api/state')['cycle']
            if cycle['phase']=='failed':raise RuntimeError(cycle['error'])
            assert len(cycle['reflections'])==3*day
            assert cycle['event_id']==event_id
            print(f'Day {day}/7: networking and three evidence-checked private reflections passed',flush=True)
            if day<7:check(host,'/api/day-cycle/next','POST',{})
        state=check(host,'/api/state')
        assert state['cycle']['phase']=='completed' and state['event']['calls']==21
        assert len(state['cycle']['reflections'])==21
        report['checks'].append('Seven day transitions, 21 network calls and 21 private bedtime reflections')
        graph=check(host,'/api/event/graph?window=3600')
        assert len(graph['nodes'])==4 and graph['edges']
        assert check(host,'/api/event/graph?window=30&offset=0')['edges']==[]
        report['checks'].append('Host monitor, four-node directed graph and sliding-window boundary')
        agent=state['event']['participants'][0]
        memories=check(host,'/api/agent-memory?agent='+agent+'&q=interests%20skills%20ideas')
        assert memories['results'],'Semantic retrieval returned no accessible memories'
        report['checks'].append('Agent-scoped local Mem0 capture and semantic retrieval with source packets')
        assert state['event']['starting_identities'][agent]==server.event.state['starting_identities'][agent]
        report.update(network_calls=state['event']['calls'],messages=state['event']['message_count'],
                      reflections=len(state['cycle']['reflections']),semantic_sources=state['semantic']['sources'],
                      final_phase=state['cycle']['phase'],elapsed_seconds=round(time.perf_counter()-started,2))
    target=ROOT/'test-results'/('residency-week-live.json' if live else 'residency-week-offline.json')
    target.parent.mkdir(exist_ok=True)
    target.write_text(json.dumps(report,indent=2))
    print(json.dumps(report,indent=2))
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--live',action='store_true')
    args=parser.parse_args()
    run(args.live)
