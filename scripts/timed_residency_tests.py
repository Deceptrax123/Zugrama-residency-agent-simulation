"""Two paced, isolated live-cohort tests. Only `run` invokes configured models.

Copies reviewed identities/preferences/allowance configuration, never live
conversations or memories. Does not connect a Site bridge or start the real event.
"""
import argparse
from collections import Counter,deque
from dataclasses import replace
import fcntl
import hashlib
import json
import os
from pathlib import Path
import secrets
import sqlite3
import sys
import threading
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'scripts')]
from runtime_settings import gateway_settings
from residency.server import ResidencyServer
from residency.cohort import LiveCohort
from residency.identity import rows
from residency.local_mem0 import AgentMem0,LocalMemoryClient
from residency.sleep_cycle import SleepCycle
from residency.hermes import Hermes
from residency.markdown_memory import write_private
from residency.graph import communication_graph,deliveries
from residency.communication_insights import topics
from overnight_three import graph_page

BASE=ROOT/'.data/preflight-residency'
SOURCE=ROOT/'.data/live-residency/state/residency.sqlite3'
MAX_RUNS=2


def save(path,value):write_private(path,json.dumps(value,ensure_ascii=False,indent=2))
def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False).encode()).hexdigest()


def source_snapshot():
    with sqlite3.connect('file:'+str(SOURCE)+'?mode=ro',uri=True) as db:
        db.row_factory=sqlite3.Row
        profiles=[]
        for row in db.execute('SELECT a.*,c.source_id,w.limit_usd,w.reserve_usd FROM agent_identities a JOIN cohort_imports c ON c.slot=a.slot JOIN agent_wallets w ON w.owner_id=a.member_id ORDER BY a.slot'):
            policy=db.execute('SELECT data FROM memory_policies WHERE owner_id=?',(row['member_id'],)).fetchone()
            if not policy:raise ValueError('A resident has no saved memory preference; nothing started')
            profiles.append({'slot':row['slot'],'source_id':row['source_id'],'identity':json.loads(row['identity_json']),
                'markdown':row['identity_markdown'],'memory_policy':json.loads(policy[0]),
                'budget':{'limit_usd':f'{row["limit_usd"]/1000000:.2f}','reserve_usd':f'{row["reserve_usd"]/1000000:.2f}'}})
    if not 2<=len(profiles)<=50:raise ValueError('Expected an enrolled live cohort')
    event=json.loads((SOURCE.parent/'host-event/state.json').read_text())
    if event['status']!='idle' or event['calls'] or event['completed_calls']:raise ValueError('Real residency must remain idle before these tests')
    return profiles


class PacedGate:
    """FIFO admission before reservation/context construction, three calls max.

    Test-only wall-clock pacing; does not rewrite model waits, topics or actions.
    Waiting threads remain cancellable through the event's normal stop loop.
    """
    def __init__(self,interval,concurrency=3):
        self.interval=interval;self.capacity=concurrency;self.inflight=0
        self.next_at=0;self.queue=deque();self.condition=threading.Condition()

    def acquire(self,timeout=.2):
        ident=threading.get_ident();end=time.monotonic()+timeout
        with self.condition:
            if ident not in self.queue:self.queue.append(ident)
            while True:
                now=time.monotonic()
                if self.queue[0]==ident and self.inflight<self.capacity and now>=self.next_at:
                    self.queue.popleft();self.inflight+=1;self.next_at=now+self.interval
                    self.condition.notify_all();return True
                remaining=end-now
                if remaining<=0:return False
                self.condition.wait(min(remaining,max(.001,self.next_at-now)))

    def release(self):
        with self.condition:self.inflight-=1;self.condition.notify_all()


def export(server,directory,report):
    host=server.sandbox.owner;event=server.event
    if not event or not event.state['event_id']:return
    with server.store.db() as db:
        messages=[dict(r) for r in db.execute('SELECT * FROM conversation_messages ORDER BY seq')]
        names={r['id']:r['name'] for r in db.execute('SELECT id,name FROM members')}
        visits=[dict(r) for r in db.execute('SELECT * FROM conversation_visits ORDER BY joined_at')]
    people=set(event.personas)|{event.npc.member_id}
    edges=deliveries(server.store,event.rooms,people);graph=communication_graph(event,host,86400)
    save(directory/'messages.json',messages);save(directory/'visits.json',visits)
    save(directory/'graph.json',{'graph':graph,'deliveries':edges})
    write_private(directory/'communication.html',graph_page(graph,edges))
    transcript=['# Isolated residency test conversations\n\nFull quotes from generated test conversations. Not commitments made by the human residents.\n']
    for m in messages:transcript.append(f'\n## Message {m["seq"]} · {names[m["sender_id"]]} · room {m["conversation_id"]}\n\n{m["body"]}\n')
    write_private(directory/'CONVERSATIONS.md',''.join(transcript))
    save(directory/'event.json',event.status(host));save(directory/'accounts.json',server.sandbox.accounts.view(host))
    save(directory/'cycle.json',server.cycle.view(host));save(directory/'memory-status.json',server.semantic.view())
    save(directory/'topics.json',topics(messages,[{'id':p,'name':i['name']} for p,i in event.personas.items()]))
    recalls={};notes={};context_checks={}
    for row in rows(server.store):
        owner=row['member_id'];target=directory/'agents'/str(row['slot']);policy=server.memory.policy(owner)
        write_private(target/'IDENTITY.md',row['identity_markdown'])
        try:
            selected=server.semantic.read_markdown(owner);save(target/'notes.json',selected)
            write_private(target/'MEMORY.md',server.semantic.export_markdown(host,owner)['markdown'])
            found=server.semantic.search(host,owner,'interests skills ideas commitments priorities disagreements')
            save(target/'recall.json',found);notes[row['identity']['name']]=len(selected['results'])
            recalls[row['identity']['name']]={'results':len(found['results']),'retrieval':found.get('retrieval'),'warning':found.get('warning')}
            packet=event.context(owner);save(target/'next-context-preview.json',packet)
            context_checks[row['identity']['name']]={'network_context':policy.get('network_context',False),'notes':len(packet.get('private_memory',[])),'reflection':bool(packet.get('previous_reflection')),'retrieval':packet.get('memory_retrieval')}
        except Exception as error:
            recalls[row['identity']['name']]={'error':type(error).__name__+': '+str(error)}
    packets=[];audit_errors=[]
    for path in sorted((directory/'calls').glob('*/*/request.json')):
        call=json.loads(path.read_text());ctx=json.loads(call['payload']['messages'][-1]['content']);packets.append(ctx)
        for note in ctx.get('private_memory',[]):
            allowed={s['key'] for s in server.semantic.sources(ctx['member_id'])}
            if any(s['key'] not in allowed for s in note.get('sources',[])):audit_errors.append('Unwitnessed memory source in '+str(path.relative_to(directory)))
        if not server.memory.policy(ctx['member_id']).get('network_context',False) and ('private_memory' in ctx or ctx.get('previous_reflection')):audit_errors.append('Memory opt-out violated')
    accounts=server.sandbox.accounts.view(host)['agents']
    report.update(event_status=event.state['status'],calls=event.state['calls'],completed_calls=event.state['completed_calls'],
        discarded_or_failed_calls=event.state['calls']-event.state['completed_calls'],messages=len(messages),rooms=len(event.rooms),
        agent_errors={names.get(k,k):v for k,v in event.state.get('agent_errors',{}).items()},npc_questions=event.npc.view(),
        speakers=dict(Counter(names[m['sender_id']] for m in messages)),reflections=len(server.cycle.view(host)['reflections']),
        cycle_phase=server.cycle.state['phase'],memory=server.semantic.view(),notes=notes,recall_checks=recalls,
        next_context_checks=context_checks,networking_requests_with_notes=sum(bool(p.get('private_memory')) for p in packets),
        networking_requests_with_reflections=sum(bool(p.get('previous_reflection')) for p in packets),
        context_audit_errors=audit_errors,request_audits=len(packets),response_audits=len(list((directory/'calls').glob('*/*/response.json'))),
        total_tokens=sum(a['wallet']['total_tokens'] for a in accounts),estimated_usd=sum(a['wallet']['spent_usd'] for a in accounts),
        held_usd=sum(a['wallet']['held_usd'] for a in accounts),
        networking_seconds=(event.state.get('finished_at') or time.time())-event.state['started_at'])
    save(directory/'summary.json',report)
    write_private(directory/'SUMMARY.md',f'# Run {report["number"]}\n\n```json\n'+json.dumps(report,indent=2,ensure_ascii=False)+'\n```\n\nSee CONVERSATIONS.md, agents/, graph.json and communication.html.\n')


def run_trial(batch,number,profiles,config,target_seconds=600,max_calls=30,backend=None,memory=None):
    if number not in (1,2):raise ValueError('Only two simulations are authorized')
    directory=batch/f'run-{number:02d}';directory.mkdir(mode=0o700)
    report={'number':number,'status':'preparing','model':config.hermes_model,'residents':len(profiles),'max_calls':max_calls,
        'target_networking_seconds':target_seconds,'started_at':time.time(),'fresh_memory_scope':True,'source_history_imported':False,
        'test_only_pacing_seconds':target_seconds/max(1,max_calls-1),'bedtime_days_tested':1,'networking_topics_assigned':False}
    config=replace(config,data_dir=directory/'state',join_code=secrets.token_urlsafe(24))
    server=ResidencyServer(('127.0.0.1',0),config,backend)
    try:
        server.sandbox=LiveCohort(server,50);server.audit_directory=directory/'calls'
        token,_=server.sandbox.signup({'name':'Isolated preflight host','email':'preflight@example.test','password':secrets.token_urlsafe(32),'join_code':config.join_code})
        host=server.sandbox.owner;server.store.logout(token)
        server.semantic=AgentMem0(server,memory);server.cycle=SleepCycle(server,server.semantic.client)
        for profile in profiles:
            server.sandbox.save_agent(host,profile['slot'],profile['identity'],profile['markdown'])
            member=next(r['member_id'] for r in rows(server.store) if r['slot']==profile['slot'])
            server.sandbox.accounts.configure(host,{'owner_id':member,**profile['budget']})
            server.memory.set_policy(member,profile['memory_policy'])
        save(directory/'starting-profiles.json',profiles);write_private(directory/'USER.md',(ROOT/'USER.md').read_text())
        server.event.gate=PacedGate(report['test_only_pacing_seconds'])
        report['status']='running';save(directory/'summary.json',report)
        start=time.monotonic();server.sandbox.start(host,{'max_calls':max_calls,'npc_enabled':True,'seven_days':True})
        deadline=start+target_seconds*1.25
        while server.event.active:
            save(directory/'progress.json',{'at':time.time(),'elapsed_seconds':round(time.monotonic()-start,1),**{k:server.event.state.get(k) for k in ('status','calls','completed_calls','message_count','agent_errors')}})
            if time.monotonic()>=deadline:server.event.stop(host);report['network_deadline_stop']=True;break
            time.sleep(min(2,max(.01,target_seconds/20)))
        for thread in server.event.threads:thread.join(185)
        if any(thread.is_alive() for thread in server.event.threads):raise RuntimeError('Networking did not drain; no retry')
        server.cycle.before_sleep(host)
        reflection_deadline=max(time.monotonic()+5,start+target_seconds*1.5)
        while server.cycle.thread.is_alive() and time.monotonic()<reflection_deadline:server.cycle.thread.join(.5)
        if server.cycle.thread.is_alive():raise RuntimeError('Bedtime exceeded test window; no retry')
        if server.cycle.state['phase']=='failed':raise RuntimeError(server.cycle.state['error'])
        report['status']='completed' if not server.event.state.get('agent_errors') else 'completed_with_errors'
    except Exception as error:
        report.update(status='failed',error=type(error).__name__+': '+str(error))
    finally:
        if server.event:
            server.event.stop(server.sandbox.owner)
            for thread in server.event.threads:thread.join(185)
        if server.cycle and server.cycle.thread and server.cycle.thread.is_alive():server.cycle.close();server.cycle.thread.join(185)
        report['finished_at']=time.time()
        try:export(server,directory,report)
        except Exception as error:report['export_error']=type(error).__name__+': '+str(error)
        save(directory/'summary.json',report);server.server_close()
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('command',choices=('run',));parser.add_argument('--batch',required=True);args=parser.parse_args()
    os.umask(0o077)
    if not args.batch or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_' for c in args.batch):raise ValueError('Use a simple batch name')
    BASE.mkdir(mode=0o700,parents=True,exist_ok=True)
    with (BASE/'batch.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        batch=BASE/args.batch;batch.mkdir(mode=0o700)
        profiles=source_snapshot();save(batch/'source-profiles.json',profiles)
        config=gateway_settings(batch/'unused',secrets.token_urlsafe(24))
        hermes=Hermes(config);hermes.check()
        if hermes.request('/health',timeout=5).get('residency_budget_guard')!='residency-usd-v1':raise ValueError('No budget guard')
        LocalMemoryClient().health()
        manifest={'status':'running','max_runs':MAX_RUNS,'max_calls_each':30,'residents':len(profiles),'source_hash':digest(profiles),'runs':[],'started_at':time.time()}
        save(batch/'manifest.json',manifest)
        for number in (1,2):
            manifest['runs'].append({'number':number,'status':'starting'});save(batch/'manifest.json',manifest)
            print(json.dumps({'event':'run_started','number':number,'at':time.time(),'residents':len(profiles)}),flush=True)
            report=run_trial(batch,number,profiles,config)
            manifest['runs'][-1]=report;save(batch/'manifest.json',manifest)
            print(json.dumps({'event':'run_finished','number':number,'status':report['status'],'calls':report.get('calls'),'messages':report.get('messages'),'error':report.get('error')}),flush=True)
        manifest.update(status='completed' if all(r['status']=='completed' for r in manifest['runs']) else 'finished_with_errors',finished_at=time.time(),live_source_unchanged=digest(source_snapshot())==manifest['source_hash'])
        save(batch/'manifest.json',manifest)
        print(json.dumps({'event':'batch_finished','status':manifest['status'],'live_source_unchanged':manifest['live_source_unchanged']}),flush=True)


if __name__=='__main__':main()
