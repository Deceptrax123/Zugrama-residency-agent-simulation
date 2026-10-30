"""Outbound-only, owner-scoped Sites views and durable human command delivery.

Constructing or publishing a bridge never starts networking. Only a separately
authenticated host Start command can invoke the existing event controller.
"""
import copy
import hashlib
import json
from pathlib import Path
import threading
import time
import urllib.request
from urllib.parse import urlsplit

from .identity import rows
from .markdown_memory import write_private
from .store import AppError,text


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):return None


class SiteBridge:
    def __init__(self,server,config_path,transport=None):
        self.server=server;self.path=Path(config_path);self.config=json.loads(self.path.read_text())
        origin=self.config['origin'];parsed=urlsplit(origin)
        if parsed.scheme!='https' or parsed.hostname!='zugrama-agent-residency.smudge0110.chatgpt.site' or parsed.path not in ('','/') or parsed.query or parsed.fragment or parsed.username:
            raise ValueError('Use the configured Zugrama Site HTTPS origin')
        if not isinstance(self.config.get('token'),str) or len(self.config['token'])<40:raise ValueError('Provide the separate bridge credential')
        self.transport=transport or self.request;self.closed=threading.Event();self.thread=None;self.last_hash=None;self.last_heartbeat=0;self.last_error=None;self.boot_at=time.time()*1000
        self.status_path=self.path.with_name('site-bridge-status.json')
        with server.store.db() as db:
            db.execute('CREATE TABLE IF NOT EXISTS site_command_receipts(id TEXT PRIMARY KEY,status TEXT NOT NULL,result TEXT,lease_token TEXT NOT NULL,acknowledged INTEGER NOT NULL DEFAULT 0)')
            db.execute("UPDATE site_command_receipts SET status='uncertain',result=? WHERE status='started'",(json.dumps({'error':'Host restarted during command execution; no automatic replay.'}),))

    def request(self,payload):
        req=urllib.request.Request(self.config['origin'].rstrip('/')+'/api/residency/bridge',data=json.dumps(payload,ensure_ascii=False).encode(),
            headers={'Authorization':'Bearer '+self.config['token'],'Content-Type':'application/json','User-Agent':'Zugrama-Residency-Bridge/1.0'})
        with urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect()).open(req,timeout=20) as response:
            body=response.read(100001)
            if len(body)>100000:raise AppError('The Site bridge response was too large',502)
            return json.loads(body)

    @staticmethod
    def bounded(view,maximum):
        view=copy.deepcopy(view);view['coverage']={'bounded_view':True,'full_records':'Retained on the residency host','trimmed':False}
        def size():return len(json.dumps(view,ensure_ascii=False).encode())
        # Public cohort descriptions repeat in every view. Shorten their previews
        # for large cohorts while preserving every resident ID and full originals.
        for key in ('directory','introductions'):
            for limit in (500,240,120,60,30):
                if len(json.dumps(view.get(key,[]),ensure_ascii=False).encode())<=maximum//3:break
                for item in view.get(key,[]):
                    for field,value in item.items():
                        if field in ('name','nickname','introduction','body','skills_offer_people','skills_need_people','subject_expertise','interests') and isinstance(value,str):item[field]=value[:limit]
                view['coverage']['trimmed']=True
        while size()>maximum:
            for key in ('messages','feed','notes','reflections','tool_runs','boards','usage','requests','rooms'):
                if view.get(key):
                    items=view[key];count=max(1,len(items)//2)
                    # Trim whole batches: removing one room and serializing
                    # the entire thousand-room preview repeatedly stalls the
                    # bridge. Usage and tool histories are newest-first.
                    if key in ('usage','requests','tool_runs','boards'):del items[-count:]
                    else:del items[:count]
                    break
            else:
                agents=view.get('agents',[])
                trimmed=False
                for agent in agents:
                    for container,key in ((agent,'notes'),(agent.get('account',{}),'usage'),(agent.get('account',{}),'requests')):
                        if container.get(key):
                            items=container[key];count=max(1,len(items)//2)
                            if key in ('usage','requests'):del items[-count:]
                            else:del items[:count]
                            trimmed=True;break
                    if trimmed:break
                if trimmed:
                    view['coverage']['trimmed']=True
                    continue
                # Dense host graphs can contain thousands of edges. Keep their
                # strongest edges in the hosted preview; local records stay full.
                graphs=view.get('graphs',[])+[w.get('graph',{}) for w in view.get('insights',{}).get('windows',[])]
                largest=max(graphs,key=lambda g:len(g.get('edges',[])),default=None)
                if largest and len(largest.get('edges',[]))>50:
                    largest['edges']=sorted(largest['edges'],key=lambda e:e.get('count',0),reverse=True)[:len(largest['edges'])//2]
                    view['coverage']['trimmed']=True
                    continue
                for window in view.get('insights',{}).get('windows',[]):
                    for key in ('timeline','mentions','topics'):
                        if window.get(key):window[key].pop();trimmed=True;break
                    if trimmed:break
                if trimmed:
                    view['coverage']['trimmed']=True
                    continue
                longest=max(agents,key=lambda a:len(a.get('identity_markdown','')),default=None)
                if longest and len(longest.get('identity_markdown',''))>1000:longest['identity_markdown']=longest['identity_markdown'][:len(longest['identity_markdown'])//2]
                elif view.get('identity_markdown') and len(view['identity_markdown'])>1000:view['identity_markdown']=view['identity_markdown'][:len(view['identity_markdown'])//2]
                else:raise AppError('The residency view exceeds its limit',413)
            view['coverage']['trimmed']=True
        return view

    def snapshots(self):
        server=self.server;host=server.sandbox.owner
        if not host:return []
        agents=rows(server.store);by_slot={a['slot']:a for a in agents}
        with server.store.db() as db:
            mappings=[dict(r) for r in db.execute('SELECT source_id,slot FROM cohort_imports')]
            enrollment_reviews={r['source_id']:{'basis':'host_reviewed_draft','source_status':'draft','reviewed_at':r['reviewed_at']} for r in db.execute('SELECT source_id,reviewed_at FROM cohort_enrollment_reviews')}
        directory=[{'id':a['member_id'],'name':a['identity']['name'],'nickname':a['identity'].get('nickname',''),'introduction':a['identity']['introduction'],
            **{key:a['identity'].get(key,'')[:500] for key in ('skills_offer_people','skills_need_people','subject_expertise','interests')}} for a in agents]
        event=server.event;status=event.status(host) if event else {'status':'idle','calls':0,'completed_calls':0,'worker_count':0,'event_id':None}
        public_status={k:status.get(k) for k in ('status','event_id','calls','completed_calls','max_calls','message_count','worker_count','model','error','quota')}
        cycle=server.cycle.view(host) if server.cycle else {'phase':'idle','day':0,'reflections':[]}
        cycle_status={k:cycle.get(k) for k in ('enabled','phase','day','days','busy','error')}
        accounts={a['owner_id']:a for a in server.sandbox.accounts.view(host)['agents']}
        notes={a['owner_id']:a for a in server.semantic.notes(host)['agents']} if server.semantic else {}
        def own_notes(owner):
            return [{'id':n['id'],'memory':n['memory'][:1600],'kind':n['kind'],
                'sources':[{'key':s['key'],'speaker_id':s.get('speaker_id'),'body':s['body'][:500]} for s in n['source_packet'][-3:]]} for n in notes.get(owner,{}).get('notes',[])[-30:]]
        intro=server.store.introductions() if status.get('event_id') else []
        if event and status.get('event_id'):
            from .graph import communication_graph
            graphs=[communication_graph(event,host,window) for window in (60,300,900)]
        else:graphs=[{'window_seconds':300,'nodes':[{'id':a['member_id'],'name':a['identity']['name'],'npc':False} for a in agents],'edges':[]}]
        tools=getattr(server,'agent_tools',None)
        common={'event':public_status,'cycle':cycle_status,'directory':directory,'introductions':intro,'model':server.settings.hermes_model,
            'capabilities':{'web_search':bool(tools),'web_read':bool(tools),'python_run':bool(tools),'shared_boards':bool(tools)}}
        rooms=set(event.rooms) if event else set();visits=[]
        if rooms:
            with server.store.db() as db:visits=[dict(r) for r in db.execute('SELECT * FROM conversation_visits WHERE conversation_id IN ('+','.join('?' for _ in rooms)+')',tuple(rooms))]
        analysis_directory=list(directory)
        if event and event.npc:analysis_directory.append({'id':event.npc.member_id,'name':'Facilitator NPC','npc':True})
        analyzer=getattr(server,'insight_analysis',None)
        host_analysis=analyzer.get(status.get('event_id'),'host') if analyzer else None
        with server.store.db() as db:
            usage=db.execute("SELECT count(*),coalesce(sum(total_tokens),0),coalesce(sum(cost_usd),0),sum(status='unknown'),sum(status='rejected') FROM agent_usage WHERE event_id=?",(status.get('event_id'),)).fetchone()
        event_usage={'requests':usage[0],'tokens':usage[1],'estimated_usd':usage[2]/1000000,'unknown_requests':usage[3] or 0,'rejected_requests':usage[4] or 0}
        host_view={**common,'event_usage':event_usage,'semantic_analysis':host_analysis,'analysis_status':analyzer.status() if analyzer else None,'role':'host','graphs':graphs,'feed':status.get('feed',[])[-80:],
            'tool_runs':tools.history()[:20] if tools else [],'boards':tools.boards() if tools else [],
            'agent_errors':status.get('agent_errors',{}),'agents':[{'member_id':a['member_id'],'slot':a['slot'],'name':a['identity']['name'],
                'identity_markdown':a['identity_markdown'],'account':accounts.get(a['member_id']),
                'notes':own_notes(a['member_id']),'memory_status':{k:v for k,v in notes.get(a['member_id'],{}).items() if k in ('processing','error','recall_enabled')}} for a in agents]}
        result=[{'owner_id':'host','data':self.bounded(host_view,600000)}]
        for mapping in mappings:
            agent=by_slot.get(mapping['slot']);owner=mapping['source_id']
            if not agent or not owner.startswith('anonymous:'):continue
            member=agent['member_id'];room_state=server.store.conversation_state(member)
            witnessed=[m for m in room_state['conversation_messages'] if m['conversation_id'] in rooms]
            from .communication_insights import communication_insights
            insights=communication_insights(member,witnessed,visits,analysis_directory,(status.get('finished_at') or time.time()) if status.get('event_id') else 0,semantic_only=bool(analyzer))
            account=accounts.get(member,{})
            scoped_analysis=analyzer.get(status.get('event_id'),member) if analyzer else None
            view={**common,'semantic_analysis':scoped_analysis,'role':'resident',**({'enrollment':enrollment_reviews[owner]} if owner in enrollment_reviews else {}),'tool_runs':tools.history(member)[:10] if tools else [],'boards':tools.boards(member) if tools else [],'agent':{'member_id':member,'name':agent['identity']['name'],'nickname':agent['identity'].get('nickname','')},
                'identity_markdown':agent['identity_markdown'],'wallet':account.get('wallet'),'usage':account.get('usage',[])[:30],'requests':account.get('requests',[])[:30],
                'notes':own_notes(member),'memory_status':{k:v for k,v in notes.get(member,{}).items() if k in ('processing','error','recall_enabled')},
                'network_context':account.get('network_context',False),'reflections':[r for r in cycle.get('reflections',[]) if r['owner_id']==member][-7:],
                'rooms':[r for r in room_state['conversations'] if r['id'] in rooms],
                'messages':witnessed[-80:],'insights':insights}
            result.append({'owner_id':owner,'data':self.bounded(view,180000)})
        return result

    def execute(self,job):
        server=self.server;host=server.sandbox.owner;kind=job['kind'];payload=job['payload'];actor=job['owner_id']
        if actor=='host':
            if job['created_at']<self.boot_at or time.time()*1000-job['created_at']>60000:raise AppError('Host control predates this connection or expired. Submit it again when connected.',409)
            if kind=='start':server.sandbox.start(host,payload)
            elif kind=='resume':server.event.resume(host)
            elif kind=='analyze':
                if not getattr(server,'insight_analysis',None):raise AppError('Semantic analysis is unavailable',503)
                server.insight_analysis.start(host,{'confirmed':True})
            elif kind=='stop':
                if server.cycle and server.cycle.state['enabled']:server.cycle.abort(host)
                elif server.event:server.event.stop(host)
            elif kind=='sleep':server.cycle.before_sleep(host)
            elif kind=='next':server.cycle.next_day(host)
            else:raise AppError('Unknown host control')
            return {'message':'Host control applied.','event_status':server.event.state['status'] if server.event else 'idle'}
        if kind!='request':raise AppError('Residents can only request actions from their own agent',403)
        with server.store.db() as db:
            row=db.execute('SELECT a.member_id FROM cohort_imports c JOIN agent_identities a ON a.slot=c.slot WHERE c.source_id=?',(actor,)).fetchone()
        if not row:raise AppError('This resident is not enrolled',403)
        member=row[0]
        if not isinstance(payload,dict) or set(payload)!={'body','target_id'}:raise AppError('Provide only a request and optional peer')
        body=text(payload['body'],'Request',4000);target=payload['target_id']
        people={a['member_id'] for a in rows(server.store)}
        if target is not None and (target not in people or target==member):raise AppError('Choose another enrolled resident')
        accounts=server.sandbox.accounts
        with accounts.lock,server.store.db() as db:
            if len(accounts.requests(member))>=20:raise AppError('This agent already has twenty open requests',409)
            request_id='site:'+job['id']
            db.execute("INSERT OR IGNORE INTO agent_requests VALUES(?,?,?,?,'queued','',?,?)",(request_id,member,target,body,time.time(),server.event.state.get('event_id') if server.event else None))
        if server.event:server.event.notify([member])
        return {'message':'Saved for your agent. It may consider, defer or decline the request when the host runs networking.','request_id':request_id}

    def handle(self,job):
        if not isinstance(job,dict) or set(job)!={'id','owner_id','kind','payload','lease_token','created_at'} or type(job['created_at']) not in (int,float) or any(not isinstance(job[k],str) or not job[k] for k in ('id','owner_id','kind','lease_token')):raise AppError('Invalid bridge command')
        with self.server.store.db() as db:
            old=db.execute('SELECT * FROM site_command_receipts WHERE id=?',(job['id'],)).fetchone()
            if old:return
            db.execute("INSERT INTO site_command_receipts VALUES(?,'started',NULL,?,0)",(job['id'],job['lease_token']))
        try:result=self.execute(job);status='completed'
        except AppError as error:result={'error':str(error)};status='failed'
        except Exception:result={'error':'Command interrupted; inspect the host. No automatic replay.'};status='uncertain'
        with self.server.store.db() as db:db.execute('UPDATE site_command_receipts SET status=?,result=? WHERE id=?',(status,json.dumps(result),job['id']))

    def acknowledge(self):
        with self.server.store.db() as db:pending=[dict(r) for r in db.execute("SELECT * FROM site_command_receipts WHERE acknowledged=0 AND status!='started'")]
        for receipt in pending:
            result=self.transport({'action':'complete','id':receipt['id'],'lease_token':receipt['lease_token'],'status':receipt['status'],'result':json.loads(receipt['result'])})
            if result.get('saved'):
                with self.server.store.db() as db:db.execute('UPDATE site_command_receipts SET acknowledged=1 WHERE id=?',(receipt['id'],))

    def tick(self):
        self.acknowledge()
        snapshots=self.snapshots();digest=hashlib.sha256(json.dumps(snapshots,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
        if digest!=self.last_hash:
            # A 50-person cohort can exceed one 4 MB request. Publish bounded
            # batches with the complete owner index so another batch is not erased.
            # Host goes last: its heartbeat acknowledges the completed publication.
            owners=[s['owner_id'] for s in snapshots];batch=[]
            for snapshot in sorted(snapshots,key=lambda s:s['owner_id']=='host'):
                payload={'action':'publish','snapshots':batch+[snapshot],'owners':owners}
                if len(json.dumps(payload,ensure_ascii=False).encode())>3800000 and batch:
                    self.transport({'action':'publish','snapshots':batch,'owners':owners});batch=[]
                batch.append(snapshot)
            if batch:self.transport({'action':'publish','snapshots':batch,'owners':owners})
            self.last_hash=digest;self.last_heartbeat=time.monotonic()
        elif time.monotonic()-self.last_heartbeat>=20:
            self.transport({'action':'heartbeat'});self.last_heartbeat=time.monotonic()
        for _ in range(4):
            job=self.transport({'action':'claim'}).get('job')
            if not job:break
            self.handle(job);self.acknowledge();self.last_hash=None

    def run(self):
        while not self.closed.is_set():
            try:self.tick();self.last_error=None
            except Exception as error:
                self.last_error='Site bridge unavailable; pending commands are not replayed automatically.'
                import traceback
                write_private(self.path.with_name('site-bridge-error.log'),traceback.format_exc())
            write_private(self.status_path,json.dumps({'at':time.time(),'connected':self.last_error is None,'error':self.last_error,'event_started_by_connection':False}))
            self.closed.wait(5)

    def start(self):
        self.thread=threading.Thread(target=self.run,daemon=True);self.thread.start()

    def close(self):
        self.closed.set()
        if self.thread:self.thread.join(25)
