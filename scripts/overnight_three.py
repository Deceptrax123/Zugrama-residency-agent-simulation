"""Two isolated seven-day trials; no retries, model switches or prior transcript import.

Only `start`/`run` invoke live models. Results persist under .data/overnight-three/.
"""
import argparse
from dataclasses import replace
import fcntl
import hashlib
import json
import os
from pathlib import Path
import secrets
import signal
import sqlite3
import subprocess
import sys
import threading
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'scripts')]
from identity_test import settings,private_json
from residency.server import ResidencyServer
from residency.sandbox import IdentitySandbox
from residency.sleep_cycle import SleepCycle
from residency.local_mem0 import AgentMem0,LocalMemoryClient
from residency.hermes import Hermes
from residency.graph import communication_graph,deliveries
from residency.markdown_memory import write_private
from residency.identity import rows as identity_rows, validate_identity, markdown as identity_markdown
from residency.store import AppError
import hermes

BASE=ROOT/'.data'/'overnight-three'
SOURCE=ROOT/'.data'/'identity-test'/'state'/'residency.sqlite3'
MAX_RUNS=2
DAILY_CALLS=(6,6,6,6,6,6,4)
MODEL='gpt-5.6-terra'
NOTICE=('Networking uses the unchanged GPT Terra route and only witnessed room history. '
        'Derived memory and bedtime reflections stay local; they are not injected into networking requests. '
        'Topics and peers are freely selected. Days are logical boundaries, not a calibrated human-time ratio. '
        'USD values are estimated API-equivalent usage, not subscription cash charges. '
        'Compass reflections are model interpretations, not validated belief-change measurements.')


def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False).encode()).hexdigest()


def source_snapshot():
    with sqlite3.connect('file:'+str(SOURCE)+'?mode=ro',uri=True) as db:
        db.row_factory=sqlite3.Row
        records=[dict(r) for r in db.execute('SELECT * FROM agent_identities ORDER BY slot')]
        if len(records)!=3:raise ValueError('Expected the three saved test identities; source was preserved')
        policies={r['owner_id']:json.loads(r['data']) for r in db.execute('SELECT * FROM memory_policies')}
        return [{'slot':r['slot'],'identity':validate_identity(json.loads(r['identity_json'])),
                 'markdown':identity_markdown(validate_identity(json.loads(r['identity_json']))),
                 'source_markdown':r['identity_markdown'],'memory_policy':policies.get(r['member_id'])} for r in records]


def location(name):
    if not name or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_' for c in name):raise ValueError('Invalid batch name')
    path=BASE/name
    if path.is_symlink() or path.resolve().parent!=BASE.resolve():raise ValueError('Invalid batch directory')
    return path


def journal(batch,event,**details):
    with (batch/'activity.jsonl').open('a') as handle:
        handle.write(json.dumps({'at':time.time(),'event':event,**details})+'\n')
    print(event+' '+json.dumps(details),flush=True)


class AuditedHermes:
    def __init__(self,inner,directory):self.inner,self.directory=inner,directory;self.settings=inner.settings
    def check(self):return self.inner.check()
    def request(self,path,payload=None,headers=None,**kwargs):
        audit=path=='/v1/chat/completions'
        if audit:
            if payload.get('model')!=MODEL:raise ValueError('Model changes are forbidden')
            number=int(headers['Idempotency-Key'].rsplit(':',1)[-1])
            target=self.directory/f'{number:03d}'
            target.mkdir(parents=True,mode=0o700)
            private_json(target/'request.json',{'at':time.time(),'path':path,'payload':payload})
        try:result=self.inner.request(path,payload,headers,**kwargs)
        except Exception as exc:
            if audit:private_json(target/'error.json',{'at':time.time(),'type':type(exc).__name__,'error':str(exc) if isinstance(exc,AppError) else 'Request failed; no retry'})
            raise
        if audit:private_json(target/'response.json',{'at':time.time(),'response':result})
        return result


class AuditedMemory:
    def __init__(self,inner,directory):self.inner,self.directory=inner,directory
    def __getattr__(self,name):return getattr(self.inner,name)
    def reflect(self,payload):
        owner=digest(payload['starting_identity'])[:12]
        target=self.directory/f'day-{payload["day"]}-{owner}'
        target.mkdir(parents=True,mode=0o700)
        private_json(target/'request.json',payload)
        result=self.inner.reflect(payload)
        private_json(target/'response.json',result)
        return result


def graph_page(graph,edges):
    data=json.dumps({'graph':graph,'deliveries':edges}).replace('<','\\u003c')
    return '''<!doctype html><html lang="en"><meta charset="utf-8"><title>Residency communication replay</title><style>body{font:17px system-ui;max-width:960px;margin:36px auto;padding:20px;background:#f8f7f1;color:#23352c}svg{width:100%;height:460px}label{margin-right:20px}input{width:65%}table{border-collapse:collapse}td,th{padding:8px;text-align:left;border-bottom:1px solid #ccc}</style><h1>Communication over time</h1><p>Arrows count delivery to joined participants, including group delivery. They do not establish individual addressing or reading.</p><label>Window <select id="window"><option value="30">30 seconds</option><option value="300" selected>5 minutes</option><option value="3600">1 hour</option><option value="86400">All (24h)</option></select></label><button id="play">Play / pause</button><p><input id="position" type="range" min="0" step="1"><output id="clock"></output></p><svg viewBox="0 0 900 460" id="plot"></svg><table><thead><tr><th>Speaker</th><th>Recipient</th><th>Deliveries</th></tr></thead><tbody id="rows"></tbody></table><script>const d=DATA;const g=d.graph,p=document.getElementById('position'),w=document.getElementById('window');p.max=Math.max(1,Math.ceil(g.duration));p.value=p.max;const names=Object.fromEntries(g.nodes.map(n=>[n.id,n.name]));const points=Object.fromEntries(g.nodes.map((n,i)=>[n.id,[450+270*Math.cos(i*2*Math.PI/g.nodes.length-Math.PI/2),230+160*Math.sin(i*2*Math.PI/g.nodes.length-Math.PI/2)]]));const ns='http://www.w3.org/2000/svg';function el(t,a,text){let e=document.createElementNS(ns,t);for(let k in a)e.setAttribute(k,a[k]);if(text)e.textContent=text;return e}function draw(){const end=g.started_at+Number(p.value),start=end-Number(w.value),counts={};for(const e of d.deliveries)if(e.at>start&&e.at<=end){let key=e.source+'|'+e.target;counts[key]=(counts[key]||0)+1}const svg=document.getElementById('plot');svg.replaceChildren();let defs=el('defs',{}),marker=el('marker',{id:'arrow',viewBox:'0 0 10 10',refX:9,refY:5,markerWidth:7,markerHeight:7,orient:'auto-start-reverse'});marker.append(el('path',{d:'M 0 0 L 10 5 L 0 10 z',fill:'#56826b'}));defs.append(marker);svg.append(defs);let table=document.getElementById('rows');table.replaceChildren();for(const [key,count]of Object.entries(counts)){let [a,b]=key.split('|'),[x,y]=points[a],[u,v]=points[b],len=Math.hypot(u-x,v-y),dx=(u-x)/len,dy=(v-y)/len;svg.append(el('line',{x1:x+dx*37-dy*7,y1:y+dy*37+dx*7,x2:u-dx*43-dy*7,y2:v-dy*43+dx*7,stroke:'#56826b','stroke-width':Math.min(10,1+Math.sqrt(count)),'marker-end':'url(#arrow)'}));svg.append(el('text',{x:(x+u)/2-dy*15,y:(y+v)/2+dx*15},String(count)));let tr=document.createElement('tr');for(let value of [names[a],names[b],count]){let td=document.createElement('td');td.textContent=value;tr.append(td)}table.append(tr)}for(const n of g.nodes){let[x,y]=points[n.id];svg.append(el('circle',{cx:x,cy:y,r:32,fill:n.npc?'#d6b883':'#d0e2d5'}));svg.append(el('text',{x,y:y+54,'text-anchor':'middle'},n.name))}document.getElementById('clock').textContent=Math.round(Number(p.value))+' s / '+Math.round(g.duration)+' s'}p.oninput=w.onchange=draw;let playing=false;document.getElementById('play').onclick=()=>{if(Number(p.value)>=Number(p.max))p.value=0;playing=!playing};setInterval(()=>{if(playing){p.value=Math.min(Number(p.max),Number(p.value)+5);draw();if(Number(p.value)>=Number(p.max))playing=false}},250);draw();</script></html>'''.replace('DATA',data)


def export_trial(server,directory,report):
    event=server.event;host=server.sandbox.owner
    if not event or not event.state['event_id']:return
    with server.store.db() as db:
        messages=[dict(r) for r in db.execute('SELECT * FROM conversation_messages ORDER BY seq')]
        names={r['id']:r['name'] for r in db.execute('SELECT id,name FROM members')}
    private_json(directory/'messages.json',messages)
    transcript=['# Conversations\n\n'+NOTICE+'\n']
    for m in messages:
        transcript.append(f'\n## {m["seq"]} · {names[m["sender_id"]]} · room {m["conversation_id"]}\n\n{m["body"]}\n')
    write_private(directory/'CONVERSATIONS.md',''.join(transcript))
    private_json(directory/'event.json',event.status(host))
    private_json(directory/'accounts.json',server.sandbox.accounts.view(host))
    cycle=server.cycle.view(host);private_json(directory/'cycle.json',cycle)
    private_json(directory/'memory-status.json',server.semantic.view())
    for row in identity_rows(server.store):
        owner=row['member_id'];target=directory/'agents'/str(row['slot'])
        write_private(target/'IDENTITY.md',row['identity_markdown'])
        notes=server.semantic.read_markdown(owner);private_json(target/'notes.json',notes)
        write_private(target/'MEMORY.md',server.semantic.export_markdown(host,owner)['markdown'])
        for f in server.semantic.markdown_path(owner).parent.glob('REFLECTION-day-*.md'):write_private(target/f.name,f.read_text())
        # Validate local semantic recall against the Markdown-backed notes; never send it to Terra.
    graph=communication_graph(event,host,window=86400)
    people=set(event.personas)|({event.npc.member_id} if event.npc and event.npc.enabled else set())
    edges=deliveries(server.store,event.rooms,people)
    private_json(directory/'graph.json',{'graph':graph,'deliveries':edges})
    write_private(directory/'communication.html',graph_page(graph,edges))
    accounts=server.sandbox.accounts.view(host)
    report.update(calls=event.state['calls'],completed_calls=event.state['completed_calls'],messages=len(messages),
                  reflections=len(cycle['reflections']),npc_questions=event.npc.view()['question_count'],
                  total_tokens=sum(a['wallet']['total_tokens'] for a in accounts['agents']),
                  estimated_usd=sum(a['wallet']['spent_usd'] for a in accounts['agents']),memory=server.semantic.view())
    private_json(directory/'summary.json',report)
    write_private(directory/'SUMMARY.md',f'# Trial {report["number"]} · {report["status"]}\n\n'+NOTICE+'\n\n```json\n'+json.dumps(report,indent=2)+'\n```\n\nSee CONVERSATIONS.md, agents/, accounts.json, calls/ and communication.html.\n')


def run_trial(batch,number,profiles,config,deadline,backend=None,memory=None):
    if type(number) is not int or number not in (1,2):raise ValueError('At most two simulation slots are permitted')
    directory=batch/f'run-{number:02d}';directory.mkdir(mode=0o700)
    report={'number':number,'status':'preparing','model':MODEL,'days':7,'max_network_calls':40,'allowance_usd_per_agent':10,'reserve_usd_per_agent':1.90,'npc_enabled':True,'day_log':[],'started_at':time.time()}
    config=replace(config,data_dir=directory/'state',join_code=secrets.token_urlsafe(24),public_origin='http://127.0.0.1:7380')
    base=backend or Hermes(config)
    server=ResidencyServer(('127.0.0.1',0),config,AuditedHermes(base,directory/'calls'))
    try:
        server.sandbox=IdentitySandbox(server)
        token,_=server.sandbox.signup({'name':'Isolated overnight test host','email':'overnight-host@example.test','password':secrets.token_urlsafe(32),'join_code':config.join_code})
        host=server.store.authenticate(token)['member_id'];server.store.logout(token)
        server.semantic=AgentMem0(server,AuditedMemory(memory or LocalMemoryClient(),directory/'reflection-calls'))
        server.cycle=SleepCycle(server,server.semantic.client)
        for profile in profiles:
            saved=server.sandbox.save_agent(host,profile['slot'],profile['identity'],profile['markdown'])
            owner=next(a['member_id'] for a in saved['agents'] if a['slot']==profile['slot'])
            server.sandbox.accounts.configure(host,{'owner_id':owner,'limit_usd':'10.00','reserve_usd':'1.90'})
            if profile['memory_policy']:server.memory.set_policy(owner,profile['memory_policy'])
        private_json(directory/'starting-personas.json',profiles)
        write_private(directory/'USER.md',(ROOT/'USER.md').read_text())
        report['status']='running';private_json(directory/'summary.json',report)
        journal(batch,'trial_started',number=number,max_calls=40)
        server.sandbox.start(host,{'max_calls':DAILY_CALLS[0],'npc_enabled':True,'seven_days':True})
        for day,daily_limit in enumerate(DAILY_CALLS,1):
            until=min(deadline,time.monotonic()+1200);sample_at=0;bounded=False
            while server.event.active:
                if time.monotonic()>=until:
                    server.event.stop(host);bounded=True;break
                if time.monotonic()>=sample_at:
                    private_json(directory/'progress.json',{'day':day,'calls':server.event.state['calls'],'completed_calls':server.event.state['completed_calls'],'message_count':server.event.state['message_count'],'at':time.time()})
                    sample_at=time.monotonic()+5
                time.sleep(.5)
            for thread in server.event.threads:thread.join(200)
            if any(t.is_alive() for t in server.event.threads):raise RuntimeError('Networking did not drain; no retry')
            if server.event.state['status']=='failed':raise RuntimeError(server.event.state['error'])
            if server.event.state['calls']>40:raise RuntimeError('Hard trial call limit exceeded')
            server.cycle.before_sleep(host)
            until=min(deadline,time.monotonic()+900)
            while server.cycle.thread.is_alive():
                if time.monotonic()>=until:raise RuntimeError('Bedtime reflection deadline exceeded; no retry')
                time.sleep(.5)
            if server.cycle.state['phase']=='failed':raise RuntimeError(server.cycle.state['error'])
            if len(server.cycle.view(host)['reflections'])!=day*3:raise RuntimeError('Missing bedtime reflections')
            report['day_log'].append({'day':day,'calls_cumulative':server.event.state['calls'],'bounded_day_stop':bounded,'reflections':day*3,'at':time.time()})
            export_trial(server,directory,report)
            journal(batch,'day_completed',number=number,day=day,calls=server.event.state['calls'],reflections=day*3)
            if day<7:
                if time.monotonic()>=deadline:raise RuntimeError('Batch time limit reached')
                server.cycle.state['networking_settings']['max_calls']=min(DAILY_CALLS[day],40-server.event.state['calls'])
                server.cycle.next_day(host)
        report['status']='completed'
        report['recall_checks']={}
        for row in identity_rows(server.store):
            result=server.semantic.search(host,row['member_id'],'interests skills ideas commitments priorities disagreements')
            report['recall_checks'][str(row['slot'])]={'results':len(result['results']),'retrieval':result.get('retrieval')}
        report['identity_unchanged']=all(row['identity']==next(p['identity'] for p in profiles if p['slot']==row['slot']) for row in identity_rows(server.store))
        if not report['identity_unchanged']:raise RuntimeError('A starting identity changed unexpectedly')
    except Exception as exc:
        report.update(status='failed',error=str(exc) if isinstance(exc,(AppError,RuntimeError,ValueError)) else type(exc).__name__+': run failed without retry')
        if server.event:
            server.event.stop(server.sandbox.owner)
            for thread in server.event.threads:thread.join(200)
        if server.cycle and server.cycle.thread and server.cycle.thread.is_alive():
            server.cycle.close();server.cycle.thread.join(190)
    finally:
        report['finished_at']=time.time()
        try:export_trial(server,directory,report)
        except Exception as exc:report['export_error']=type(exc).__name__
        private_json(directory/'summary.json',report)
        server.server_close()
        if server.semantic:server.semantic.thread.join(2)
        journal(batch,'trial_finished',number=number,status=report['status'],calls=report.get('calls',0),reflections=report.get('reflections',0))
    return report


def batch_summary(batch,manifest):
    private_json(batch/'manifest.json',manifest)
    parts=['# Two three-agent residency simulations\n\n'+NOTICE+'\n',f'\nStatus: **{manifest["status"]}**. Maximum: two simulations, 40 networking calls each.\n']
    for report in manifest['runs']:
        n=report['number'];parts.append(f'\n## Run {n} · {report["status"]}\n\nCalls: {report.get("calls",0)}; messages: {report.get("messages",0)}; reflections: {report.get("reflections",0)}; tokens: {report.get("total_tokens",0)}; estimated USD: {report.get("estimated_usd",0):.4f}.\n\n[Summary](run-{n:02d}/SUMMARY.md) · [Conversations](run-{n:02d}/CONVERSATIONS.md) · [Communication replay](run-{n:02d}/communication.html)\n')
        if report.get('error'):parts.append('\nError: '+report['error']+'\n')
    write_private(batch/'README.md',''.join(parts))


def run(name):
    batch=location(name)
    with (batch/'batch.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        manifest=json.loads((batch/'manifest.json').read_text())
        if manifest['status']!='prepared' or manifest['runs']:raise ValueError('This batch was already attempted; refusing to repeat any simulations')
        profiles=json.loads((batch/'starting-personas.json').read_text())
        if digest(profiles)!=manifest['source_hash']:raise ValueError('Starting personas changed after setup')
        config=settings(7360)
        h=Hermes(config);h.check()
        if h.request('/health',timeout=5).get('residency_budget_guard')!='residency-usd-v1':raise ValueError('Budget guard unavailable; no model call sent')
        LocalMemoryClient().health()
        manifest.update(status='running',started_at=time.time());batch_summary(batch,manifest)
        deadline=time.monotonic()+21600
        for number in range(1,MAX_RUNS+1):
            if time.monotonic()>=deadline:break
            # Record consumption of a run slot BEFORE it can dispatch a model call.
            manifest['runs'].append({'number':number,'status':'starting'});batch_summary(batch,manifest)
            try:report=run_trial(batch,number,profiles,config,deadline)
            except Exception as exc:report={'number':number,'status':'failed','error':type(exc).__name__+' during setup; no retry'}
            manifest['runs'][-1]=report;batch_summary(batch,manifest)
        manifest.update(status='completed' if len(manifest['runs'])==MAX_RUNS and all(r['status']=='completed' for r in manifest['runs']) else 'finished_with_errors',finished_at=time.time(),source_personas_unchanged=digest(source_snapshot())==manifest['source_hash'])
        batch_summary(batch,manifest)
        journal(batch,'batch_finished',status=manifest['status'],simulations=len(manifest['runs']))


def start():
    os.umask(0o077);BASE.mkdir(parents=True,exist_ok=True,mode=0o700)
    with (BASE/'launch.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        latest=BASE/'latest.json'
        if latest.exists():
            previous=json.loads(latest.read_text());pid=previous.get('pid')
            try:
                args=(Path('/proc')/str(pid)/'cmdline').read_bytes().split(b'\0')
                if str(Path(__file__).resolve()).encode() in args and b'run' in args:raise ValueError('An overnight batch is already running; no extra simulations started')
            except FileNotFoundError:pass
        name=time.strftime('%Y%m%dT%H%M%SZ',time.gmtime())+'-'+secrets.token_hex(3)
        batch=location(name);batch.mkdir(mode=0o700)
        profiles=source_snapshot();private_json(batch/'starting-personas.json',profiles)
        manifest={'status':'prepared','max_simulations':MAX_RUNS,'max_calls_per_simulation':40,'source_hash':digest(profiles),'created_at':time.time(),'model':MODEL,'runs':[]}
        batch_summary(batch,manifest)
        with (batch/'worker.log').open('ab') as log:
            child=subprocess.Popen([sys.executable,'-B',str(Path(__file__).resolve()),'run','--name',name],cwd=ROOT,env=hermes.environment(),stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
        private_json(latest,{'name':name,'pid':child.pid,'directory':str(batch)})
        time.sleep(1)
        if child.poll() is not None:raise ValueError('Batch could not start; inspect its worker.log. No automatic retry was made.')
        return {'status':'running','name':name,'pid':child.pid,'directory':str(batch),'max_simulations':MAX_RUNS,'max_network_calls':80,'model':MODEL}


def status():
    saved=json.loads((BASE/'latest.json').read_text());batch=location(saved['name'])
    manifest=json.loads((batch/'manifest.json').read_text())
    for run in manifest['runs']:
        directory=batch/f'run-{run["number"]:02d}'
        summary=directory/'summary.json'
        if summary.exists():run.update(json.loads(summary.read_text()))
        progress=directory/'progress.json'
        if progress.exists() and run['status'] not in ('completed','failed'):run['progress']=json.loads(progress.read_text())
    return {**saved,**manifest}


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('command',choices=('start','run','status'));parser.add_argument('--name')
    args=parser.parse_args()
    if args.command=='run':
        if not args.name:parser.error('run requires --name')
        return run(args.name)
    print(json.dumps(start() if args.command=='start' else status(),indent=2))


if __name__=='__main__':main()
