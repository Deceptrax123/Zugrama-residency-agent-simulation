"""Read-only event mirror for the shared live screen. No model or event controls."""
import collections,hashlib,json,os,pathlib,sqlite3,time,urllib.request
ROOT=pathlib.Path(__file__).resolve().parents[1]

def artifacts_from(db,event,rooms):
    # Whitelist tool types, never publish general arguments/results: person notes
    # and recall outputs must remain private even when new tools are added.
    artifacts=[]
    for row in db.execute("SELECT id,owner_id,call_number,arguments,result,status,created_at FROM agent_tool_runs WHERE event_id=? AND name='python_run'",(event,)):
        args=json.loads(row['arguments']);result=json.loads(row['result']) if row['result'] else {};data=result.get('data') or {}
        output=json.dumps(data.get('result'),ensure_ascii=False,indent=2) if 'result' in data else ''
        if len(output)>30000:output=output[:29960]+'\n[Output excerpt truncated]'
        artifacts.append({'id':'python:'+row['id'],'kind':'python','owner_id':row['owner_id'],'room_id':None,'created_at':row['created_at'],'data':{'code':args.get('code','')[:16000],'call_number':row['call_number'],'status':row['status'],'stdout':data.get('stdout','')[:12000],'output':output,'error':result.get('error','')[:2000]}})
    for row in db.execute('SELECT id,room_id,owner_id,message_id,body,created_at FROM agent_boards WHERE event_id=?',(event,)):
        if row['room_id'] not in rooms:continue
        body=json.loads(row['body'])
        artifacts.append({'id':'board:'+row['id'],'kind':'board','owner_id':row['owner_id'],'room_id':row['room_id'],'created_at':row['created_at'],'data':{k:body.get(k,[] if k in ('equations','shapes') else '') for k in ('title','text','equations','shapes')}|{'message_id':row['message_id']}})
    tables={r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if {'agent_workspaces','workspace_revisions'}<=tables:
        for row in db.execute('SELECT w.id,w.room_id,w.title,r.* FROM agent_workspaces w JOIN workspace_revisions r ON r.workspace_id=w.id WHERE w.event_id=?',(event,)):
            if row['room_id'] in rooms:artifacts.append({'id':'workspace:'+row['id']+':'+str(row['revision']),'kind':'workspace','owner_id':row['owner_id'],'room_id':row['room_id'],'created_at':row['created_at'],'data':{'workspace_id':row['id'],'title':row['title'],'state':row['body'],'status':row['status'],'revision':row['revision'],'message_id':row['message_id']}})
    if 'allowance_transfers' in tables:
        for row in db.execute('SELECT * FROM allowance_transfers WHERE event_id=?',(event,)):
            artifacts.append({'id':'transfer:'+row['id'],'kind':'transfer','owner_id':row['from_owner'],'room_id':row['conversation_id'],'created_at':row['created_at'],'data':{'recipient_id':row['to_owner'],'amount_usd':row['amount_usd']/1000000,'reason':row['reason'],'workspace_id':row['workspace_id'],'call_number':row['call_number']}})
    return sorted(artifacts,key=lambda a:(a['created_at'],a['id']))

def room_membership(visits,residents):
    changes=[]
    for v in visits:
        changes.append({'member_id':v['member_id'],'kind':'joined','at':v['joined_at']})
        if v['left_at'] is not None:changes.append({'member_id':v['member_id'],'kind':'left','at':v['left_at']})
    changes.sort(key=lambda c:(c['at'],0 if c['kind']=='left' else 1,c['member_id']))
    active=set();peak=0
    for c in changes:
        if c['kind']=='joined':active.add(c['member_id'])
        else:active.discard(c['member_id'])
        peak=max(peak,len(active & residents))
    return {'active_participants':sorted({v['member_id'] for v in visits if v['left_after_seq'] is None}),
        'peak_residents':peak,'membership_changes':changes[-100:],'membership_change_count':len(changes)}

def capture(root=ROOT,include_artifacts=False,state_path=None):
    base=root/'.data/live-residency';path=state_path or base/'state/host-event/state.json';state=json.loads(path.read_text());event=state.get('event_id');rooms=set(state.get('conversation_ids',[]));now=time.time()
    db=sqlite3.connect('file:'+str(base/'state/residency.sqlite3')+'?mode=ro',uri=True);db.row_factory=sqlite3.Row;db.execute('BEGIN')
    identities=state.get('starting_identities',{});names={r['id']:r['name'] for r in db.execute('SELECT id,name FROM members')}
    messages=[dict(r) for r in db.execute('SELECT id,seq,conversation_id,sender_id,body,created_at FROM conversation_messages ORDER BY seq') if r['conversation_id'] in rooms]
    visits=collections.defaultdict(list)
    for row in db.execute('SELECT conversation_id,member_id,joined_after_seq,left_after_seq,joined_at,left_at FROM conversation_visits'):
        if row['conversation_id'] in rooms:visits[row['conversation_id']].append(dict(row))
    by_room=collections.defaultdict(list)
    for m in messages:
        by_room[m['conversation_id']].append(m)
        m['recipients']=sorted({v['member_id'] for v in visits[m['conversation_id']] if v['member_id']!=m['sender_id'] and m['seq']>v['joined_after_seq'] and (v['left_after_seq'] is None or m['seq']<=v['left_after_seq'])})
    ended={r['owner_id'] for r in db.execute('SELECT owner_id FROM agent_wallets WHERE ended=1')};errors=state.get('agent_errors',{});thinking=set(state.get('thinking',[]))
    directory=[{'id':owner,'name':names.get(owner,p['name']),'nickname':p.get('nickname',''),'state':'error' if owner in errors else 'responding' if owner in thinking else 'ended' if owner in ended else 'waiting'} for owner,p in identities.items()]
    extras=({m['sender_id'] for m in messages}|{v['member_id'] for values in visits.values() for v in values})-set(identities)
    directory.extend({'id':owner,'name':names.get(owner,'Facilitator NPC'),'nickname':'','state':'facilitator'} for owner in sorted(extras))
    room_rows=[{**room_membership(visits[room],set(identities)),'id':room,'participants':sorted({v['member_id'] for v in visits[room]}),'message_count':len(by_room[room]),'last_at':by_room[room][-1]['created_at'] if by_room[room] else 0,'last_seq':by_room[room][-1]['seq'] if by_room[room] else 0} for room in rooms]
    tools=[dict(r) for r in db.execute('SELECT owner_id,name,status,created_at FROM agent_tool_runs WHERE event_id=? ORDER BY created_at DESC LIMIT 20',(event,))]
    artifacts=artifacts_from(db,event,rooms) if include_artifacts else []
    db.rollback();db.close()
    if json.loads(path.read_text()).get('event_id')!=event:raise RuntimeError('Event changed during capture; no snapshot published')
    snapshot={'event_id':event,'status':state.get('status','idle'),'started_at':state.get('started_at'),'captured_at':now,'message_count':len(messages),'completed_calls':state.get('completed_calls',0),'thinking':list(thinking & set(identities)),'directory':directory,'rooms':sorted(room_rows,key=lambda r:r['last_seq'],reverse=True),'tools':tools,'new_additions':state.get('new_additions',[])}
    return (snapshot,messages,artifacts) if include_artifacts else (snapshot,messages)

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):return None

class WatchMirror:
    def __init__(self,root=ROOT):
        self.root=root;self.config=json.loads((root/'.data/live-residency/site-bridge.json').read_text());self.event=None;self.cursor=0;self.artifact_hashes={}
        self.opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect());self.status_file=root/'.data/live-residency/watch-bridge/status.json'
    def request(self,payload):
        req=urllib.request.Request(self.config['origin']+'/api/watch/bridge',data=json.dumps(payload,ensure_ascii=False).encode(),headers={'Authorization':'Bearer '+self.config['token'],'Content-Type':'application/json','User-Agent':'Mozilla/5.0 (Zugrama Live Watch)'})
        with self.opener.open(req,timeout=30) as response:return json.load(response)
    def tick(self):
        state,messages,artifacts=capture(self.root,include_artifacts=True)
        if not state['event_id']:return
        if self.event!=state['event_id']:
            saved=self.request({'action':'status','event_id':state['event_id']});self.cursor=int(saved['last_seq']);self.event=state['event_id'];self.artifact_hashes={}
        fresh=[m for m in messages if m['seq']>self.cursor]
        for offset in range(0,max(1,len(fresh)),40):
            batch=fresh[offset:offset+40];response=self.request({'action':'publish','state':state,'messages':batch})
            if response.get('saved') is not True:raise RuntimeError('Live mirror publication was not acknowledged')
            if batch:self.cursor=batch[-1]['seq']
        fresh_artifacts=[(a,hashlib.sha256(json.dumps(a,sort_keys=True).encode()).hexdigest()) for a in artifacts]
        fresh_artifacts=[(a,h) for a,h in fresh_artifacts if self.artifact_hashes.get(a['id'])!=h]
        for offset in range(0,len(fresh_artifacts),20):
            batch=fresh_artifacts[offset:offset+20];response=self.request({'action':'publish','state':state,'messages':[],'artifacts':[a for a,h in batch]})
            if response.get('saved') is not True:raise RuntimeError('Artifact publication was not acknowledged')
            self.artifact_hashes.update({a['id']:h for a,h in batch})
        self.status_file.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
        self.status_file.write_text(json.dumps({'event_id':self.event,'last_seq':self.cursor,'source_messages':len(messages),'source_artifacts':len(artifacts),'published_at':time.time(),'model_calls':0}));self.status_file.chmod(0o600)
    def run(self):
        while True:
            try:self.tick()
            except Exception as e:
                print('Live watch mirror unavailable: '+type(e).__name__+'; simulation is unaffected.',flush=True)
            time.sleep(5)

if __name__=='__main__':
    os.umask(0o077);WatchMirror().run()
