"""App-local Mem0 transport and access-scoped asynchronous conversation capture."""
import hashlib
import json
from pathlib import Path
import queue
import sqlite3
import threading
import urllib.error
import urllib.request

from .config import APP_ROOT
from .store import AppError
from .hermes import NoRedirect

SERVICE = APP_ROOT/'.data/local-memory/service.json'


class LocalMemoryClient:
    def __init__(self, config=None):
        self.config = config or json.loads(SERVICE.read_text())
        if self.config['url'] != 'http://127.0.0.1:7371':
            raise ValueError('The memory service must be the dedicated loopback endpoint')

    def request(self, route, payload=None):
        request = urllib.request.Request(self.config['url']+route,
            data=None if payload is None else json.dumps(payload,ensure_ascii=False).encode(),
            headers={'Content-Type':'application/json', 'Authorization':'Bearer '+self.config['key']})
        try:
            with urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect()).open(request, timeout=180) as response:
                raw=response.read(5_000_001)
                if len(raw)>5_000_000:raise ValueError('Oversized local memory response')
                return json.loads(raw)
        except (OSError, ValueError, urllib.error.URLError):
            raise AppError('Local memory service unavailable or returned an invalid response; no retry was made', 502) from None

    def health(self): return self.request('/health')
    def add(self, scope, sources, priorities):
        return self.request('/add', {'scope':scope,'sources':sources,'priorities':priorities})
    def search(self, scope, query): return self.request('/search', {'scope':scope,'query':query})
    def list_notes(self, scope): return self.request('/list', {'scope':scope})
    def reflect(self, payload): return self.request('/reflect', payload)


class AgentMem0:
    def __init__(self, server, client=None):
        self.server, self.client = server, client or LocalMemoryClient()
        self.queue = queue.Queue(maxsize=128)
        self.closed = threading.Event()
        self.lock = threading.RLock()
        self.requested_owners=set()
        with server.store.db() as db:
            db.execute('''CREATE TABLE IF NOT EXISTS mem0_sources(
                scope TEXT, source_key TEXT, owner_id TEXT, status TEXT, error TEXT,
                PRIMARY KEY(scope,source_key))''')
            db.execute("UPDATE mem0_sources SET status='interrupted',error='App restarted; no automatic retry' WHERE status='queued'")
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def scope(self, owner):
        event = self.server.event
        if not event or owner not in event.personas or not event.state['event_id']:
            raise AppError('Choose an agent in a started event', 409)
        return hashlib.sha256(f'{self.server.store.instance_id}:{event.state["event_id"]}:{owner}'.encode()).hexdigest()

    def sources(self, owner):
        event = self.server.event
        if not event or owner not in event.personas: return []
        rooms = set(event.rooms)
        visible = {message['id'] for message in self.server.store.conversation_state(owner)['conversation_messages']
                   if message['conversation_id'] in rooms}
        return [source for source in self.server.memory.sources(owner, pending_only=False)
                if source['kind']=='joined_conversation' and source['key'].split(':')[1] in visible]

    def enqueue(self, owners):
        with self.lock:self.requested_owners.update(owners)
        for owner in owners:
            if self.closed.is_set() or not self.server.memory.policy(owner)['capture_conversations']: continue
            try:
                scope = self.scope(owner)
            except AppError:
                continue
            with self.lock, self.server.store.db() as db:
                known = {row[0] for row in db.execute('SELECT source_key FROM mem0_sources WHERE scope=?', (scope,))}
                sources, size = [], 0
                for source in self.sources(owner):
                    if source['key'] in known: continue
                    if len(sources)>=12 or size+len(source['body'])>12000: break
                    sources.append(source); size+=len(source['body'])
                if not sources: continue
                if self.queue.full(): continue  # New writes can schedule still-unreserved sources later.
                for source in sources:
                    db.execute("INSERT INTO mem0_sources VALUES(?,?,?,'queued',NULL)", (scope,source['key'],owner))
                self.queue.put_nowait((owner,scope,sources))

    def _run(self):
        while not self.closed.is_set():
            try: job=self.queue.get(timeout=.2)
            except queue.Empty: continue
            owner,scope,sources=job
            try:
                # Recheck capture, exclusions, event scope, and source access at dispatch time.
                allowed = {s['key'] for s in self.sources(owner)}
                selected = [s for s in sources if s['key'] in allowed]
                if self.scope(owner)!=scope or not self.server.memory.policy(owner)['capture_conversations']:
                    selected=[]
                if selected:
                    self.client.add(scope,selected,self.server.memory.policy(owner))
                    if self.scope(owner)==scope:self.sync_markdown(owner)
                status,error='completed',None
            except Exception:
                status,error='failed','Local Mem0 processing failed; no automatic retry'
            try:
                if not self.closed.is_set():
                    try:self._record_result(scope,sources,status,error)
                    except Exception:
                        # Extraction may have succeeded. Retain the known-source
                        # reservation and never replay a model call just because
                        # its local status could not be committed.
                        import traceback
                        from .markdown_memory import write_private
                        try:write_private(self.server.settings.data_dir/'memory-worker-error.log',traceback.format_exc())
                        except OSError:pass
                # Drain unreserved tail sources; failed/known sources are not
                # submitted to extraction again.
                if not self.closed.is_set():
                    try:self.enqueue(list(self.requested_owners))
                    except Exception:pass
            finally:
                self.queue.task_done()

    def _record_result(self,scope,sources,status,error):
        # Retry only this idempotent local transaction, never client.add().
        for attempt in range(3):
            try:
                with self.server.store.db() as db:
                    for source in sources:
                        db.execute('UPDATE mem0_sources SET status=?,error=? WHERE scope=? AND source_key=?',
                                   (status,error,scope,source['key']))
                return
            except sqlite3.OperationalError as exc:
                if not any(word in str(exc).lower() for word in ('locked','busy')) or attempt==2:raise
                if self.closed.wait(.05*(attempt+1)):raise

    def search(self, actor, owner, query):
        self.server.sandbox.authorize(actor)
        if not self.server.event or not self.server.event.state.get('event_id') or owner not in self.server.event.personas:raise AppError('Choose one of this event’s agents')
        if not isinstance(query,str) or len(query)>1000: raise AppError('Use a query of at most 1000 characters')
        policy=self.server.memory.policy(owner)
        if not policy['recall_enabled']: return {'results':[]}
        note_path=self.markdown_path(owner)
        try:result=self.read_markdown(owner)
        except AppError:
            return {'results':[],'retrieval':'local_markdown_unavailable','warning':'Saved notes could not be loaded; this turn continues without memory. No source or note was invented.'}
        try:
            ranked=self._visible_notes(owner,self.client.search(self.scope(owner),query),policy)['results']
            stored={note['id']:note for note in result['results']}
            if any(note['id'] not in stored for note in ranked):
                # Recover the local materialization without re-extracting a CV,
                # conversation or embedding; list is a read-only Mem0 operation.
                self.sync_markdown(owner);stored={note['id']:note for note in self.read_markdown(owner)['results']}
                if any(note['id'] not in stored for note in ranked):
                    # get_all is bounded. A valid ranked note outside its first
                    # page must still be materialized, rather than silently lost.
                    from .markdown_memory import document,write_private
                    for note in ranked:stored.setdefault(note['id'],note)
                    serial=[{key:n.get(key) for key in ('id','memory','created_at','updated_at')}|{'metadata':{'source_keys':[source['key'] for source in n['source_packet']]}} for n in stored.values()]
                    with self.lock:write_private(note_path,document(serial))
            result['results']=[{**stored[note['id']],'score':note['score']} for note in ranked if note['id'] in stored][:20]
            result['retrieval']='local_markdown_with_mem0_semantic_ranking'
        except AppError:
            import re
            terms=set(re.findall(r'\w+',query.casefold()))
            result['results']=sorted(result['results'],key=lambda n:len(terms&set(re.findall(r'\w+',n['memory'].casefold()))),reverse=True)[:6]
            result['retrieval']='local_markdown_lexical_fallback'
            result['warning']='Semantic ranking is unavailable; using saved Markdown notes. No model retry was made.'
        return result

    def markdown_path(self, owner):
        return self.server.settings.data_dir/'agent-memory'/self.scope(owner)/'MEMORY.md'

    def sync_markdown(self,owner):
        from .markdown_memory import document,write_private
        scope=self.scope(owner)
        policy=self.server.memory.policy(owner)
        # Preserve the existing file without reading or replacing notes when
        # recall is disabled. Re-enabling can then retrieve the prior memory.
        if not policy['recall_enabled']:return
        result=self.client.list_notes(scope) if policy['recall_enabled'] else {'results':[]}
        notes=self._visible_notes(owner,result,policy)['results']
        serial=[{key:note.get(key) for key in ('id','memory','created_at','updated_at')}|{'metadata':{'source_keys':[source['key'] for source in note['source_packet']]}} for note in notes]
        with self.lock:
            if self.scope(owner)!=scope:raise AppError('The event changed while preparing memory',409)
            write_private(self.markdown_path(owner),document(serial))

    def read_markdown(self,owner):
        from .markdown_memory import read_notes
        policy=self.server.memory.policy(owner)
        if not policy['recall_enabled']:return {'results':[],'engine':'local_markdown','external_processing':False}
        if not self.server.event or not self.server.event.state.get('event_id'):return {'results':[],'engine':'local_markdown','external_processing':False}
        with self.lock:
            path=self.markdown_path(owner)
            if not path.exists():self.sync_markdown(owner)
            try:return self._visible_notes(owner,{'results':read_notes(path)},policy)
            except (ValueError,KeyError,TypeError):
                # Retain evidence of a malformed file and rebuild from scoped Mem0.
                from .markdown_memory import write_private
                write_private(path.with_suffix('.corrupt.md'),path.read_text())
                self.sync_markdown(owner)
                return self._visible_notes(owner,{'results':read_notes(path)},policy)

    def export_markdown(self,actor,owner):
        from .markdown_memory import document,reflection_document
        self.server.sandbox.authorize(actor)
        if not self.server.event or owner not in self.server.event.personas:raise AppError('Choose one of this event’s agents')
        notes=self.read_markdown(owner)['results']
        markdown=document(notes)
        policy=self.server.memory.policy(owner)
        cycle=getattr(self.server,'cycle',None)
        if cycle and cycle.state['event_id']==self.server.event.state['event_id'] and policy['recall_enabled']:
            from .memory import excluded
            for reflection in cycle.view(actor)['reflections']:
                if reflection['owner_id']==owner and not excluded(json.dumps(reflection),policy):
                    markdown+='\n'+reflection_document(reflection['day'],reflection['body'])
        return {'filename':'MEMORY.md','markdown':markdown,'owner_id':owner,'event_id':self.server.event.state['event_id'],'external_processing':False}

    def _visible_notes(self,owner,result,policy):
        from .memory import excluded
        allowed={s['key']:s for s in self.sources(owner)}
        verified=[]
        for item in result.get('results',[]):
            if not isinstance(item,dict) or not isinstance(item.get('memory'),str) or not isinstance(item.get('id'),str):continue
            metadata=item.get('metadata') or {}
            if not isinstance(metadata,dict):continue
            keys=metadata.get('source_keys',[])
            if not isinstance(keys,list) or not keys or any(not isinstance(key,str) or key not in allowed for key in keys):continue
            if excluded(json.dumps(item),policy): continue
            verified.append({'id':item['id'],'memory':item['memory'], 'score':item.get('score'),
                             'created_at':item.get('created_at'),'updated_at':item.get('updated_at'),
                             'source_packet':[allowed[key] for key in keys], 'kind':'model_extracted_unverified'})
        return {'results':verified, 'engine':'mem0_local', 'external_processing':False}

    def notes(self,actor):
        self.server.sandbox.authorize(actor)
        event=self.server.event
        if not event or not event.state['event_id']:return {'agents':[]}
        event_id=event.state['event_id']
        agents=[]
        for owner,persona in event.personas.items():
            policy=self.server.memory.policy(owner)
            entry={'owner_id':owner,'name':persona['name'],'notes':[],'recall_enabled':policy['recall_enabled']}
            with self.server.store.db() as db:
                entry['processing']=dict(db.execute('SELECT status,count(*) FROM mem0_sources WHERE scope=? GROUP BY status',(self.scope(owner),)))
            if policy['recall_enabled']:
                try:
                    result=self.read_markdown(owner)
                    entry['notes']=sorted(result['results'],key=lambda item:str(item.get('updated_at') or item.get('created_at') or ''),reverse=True)
                except AppError as error:entry['error']=str(error)
            agents.append(entry)
        if event.state['event_id']!=event_id:agents=[]
        return {'event_id':event_id,'agents':agents,'engine':'mem0_local','external_processing':False}

    def view(self):
        with self.server.store.db() as db:
            rows=db.execute('SELECT status,count(*) FROM mem0_sources GROUP BY status').fetchall()
        return {'engine':'mem0_local','model':'qwen3-4b','embedder':'qwen3-embedding-0.6b',
                'sources':dict(rows),'queued_jobs':self.queue.qsize(),'external_processing':False}

    def close(self):
        self.closed.set()
        if self.thread is not threading.current_thread():self.thread.join(3)
