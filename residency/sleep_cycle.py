"""Seven simulated days with host-controlled bedtime and local reflection.

No wall-clock compression ratio is assumed and no event auto-starts on reload.
"""
import json
import threading
import time

from .store import AppError, text

CATEGORIES=('takeaways','view_changes','unresolved_questions','tomorrow_intentions')


def validate_reflection(value, sources):
    if not isinstance(value,dict) or set(value)!={'summary',*CATEGORIES}:
        raise AppError('Local reflection returned an invalid structure',502)
    result={'summary':text(value['summary'],'Reflection summary',2000)}
    ids={source['id'] for source in sources}
    for category in CATEGORIES:
        items=value[category]
        if not isinstance(items,list) or len(items)>6: raise AppError('Invalid reflection points',502)
        result[category]=[]
        for item in items:
            if not isinstance(item,dict) or set(item)!={'text','source_ids'}:
                raise AppError('Reflection points require text and source IDs',502)
            evidence=item['source_ids']
            if not isinstance(evidence,list) or not 1<=len(evidence)<=6 or any(not isinstance(key,str) or key not in ids for key in evidence):
                raise AppError('Reflection cited a conversation the agent did not witness',502)
            result[category].append({'text':text(item['text'],'Reflection point',1200),'source_ids':list(dict.fromkeys(evidence))})
    return result


class SleepCycle:
    def __init__(self, server, client):
        self.server,self.client=server,client
        self.lock=threading.RLock();self.closed=threading.Event();self.thread=None
        self.state={'enabled':False,'days':7,'day':0,'phase':'idle','event_id':None,'error':None}
        with server.store.db() as db:
            db.execute('''CREATE TABLE IF NOT EXISTS sleep_reflections(
                event_id TEXT, day INTEGER, owner_id TEXT, body TEXT, sources TEXT,
                model TEXT, created_at REAL, PRIMARY KEY(event_id,day,owner_id))''')
            saved=db.execute("SELECT value FROM metadata WHERE key='sleep_cycle'").fetchone()
        if saved:self.state.update(json.loads(saved[0]))
        event=server.event
        awaiting_bedtime=(self.state['phase']=='awake' and event
            and event.state.get('event_id')==self.state.get('event_id')
            and event.state.get('status') in ('completed','completed_with_errors','paused_quota','stopped'))
        if self.state['phase'] in ('awake','ending_day','reflecting') and not awaiting_bedtime:
            self.state['phase']='interrupted'
            self.state['error']='App restarted; no automatic day or reflection resumption'
            self._save()

    def _save(self):
        with self.server.store.db() as db:
            db.execute("INSERT INTO metadata VALUES('sleep_cycle',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",(json.dumps(self.state),))

    def view(self, actor):
        self.server.sandbox.authorize(actor)
        with self.lock,self.server.store.db() as db:
            reflections=[{**dict(row),'body':json.loads(row['body']),'sources':json.loads(row['sources'])}
                         for row in db.execute('SELECT * FROM sleep_reflections WHERE event_id=? ORDER BY day,owner_id',(self.state['event_id'],))]
            return {**self.state,'reflections':reflections,'busy':bool(self.thread and self.thread.is_alive()),
                    'wall_clock_scale':None,'reflection_model':'local qwen3-4b',
                    'memory':self.server.semantic.view() if self.server.semantic else None}

    def start(self, actor, payload):
        self.server.sandbox.authorize(actor)
        with self.lock:
            if self.thread and self.thread.is_alive():raise AppError('Before-sleep reflection is still running',409)
            self.closed.clear()
            event=self.server.event
            if not event:raise AppError('Save three agent identities first',409)
            previous=dict(self.state)
            self.state={'enabled':True,'days':7,'day':1,'phase':'awake','event_id':event.state['event_id'],
                        'day_start_seq':0,'networking_settings':dict(payload),'error':None}
            try:result=event.start(actor,payload)
            except Exception:
                self.state=previous
                raise
            self.state['event_id']=event.state['event_id']
            self._save()
            return result

    def before_sleep(self, actor):
        self.server.sandbox.authorize(actor)
        with self.lock:
            if not self.state['enabled'] or self.state['phase']!='awake':
                raise AppError('Before-sleep reflection is available once per awake simulated day',409)
            self.state['phase']='ending_day';self.state['error']=None;self._save()
            self.server.event.stop(actor)
            self.thread=threading.Thread(target=self._reflect_day,daemon=True)
            self.thread.start()
        return self.view(actor)

    def _reflect_day(self):
        try:
            event=self.server.event
            for thread in event.threads:
                while thread.is_alive():
                    thread.join(.2)
                    if self.closed.is_set():return
            if self.server.semantic:
                deadline=time.monotonic()+min(1200,max(180,self.server.semantic.queue.unfinished_tasks*30))
                while self.server.semantic.queue.unfinished_tasks:
                    if self.closed.wait(.2):return
                    if time.monotonic()>deadline:raise AppError('Local memory queue did not drain before sleep; no retry',502)
            with self.lock:
                if self.closed.is_set():return
                self.state['phase']='reflecting';self._save()
                day,event_id,boundary=self.state['day'],self.state['event_id'],self.state['day_start_seq']
            for owner in event.personas:
                if self.closed.is_set():return
                capture=self.server.memory.policy(owner)['capture_conversations']
                messages=[m for m in self.server.store.conversation_state(owner)['conversation_messages']
                          if m['conversation_id'] in event.rooms and m['seq']>boundary] if capture else []
                # Private daily packet has a disclosed context bound.
                sources=[];size=0
                for message in reversed(messages[-20:]):
                    if size+len(message['body'])>12000:break
                    sources.append(message);size+=len(message['body'])
                sources.reverse()
                with self.server.store.db() as db:
                    prior=db.execute('SELECT body FROM sleep_reflections WHERE event_id=? AND owner_id=? AND day<? ORDER BY day DESC LIMIT 1',
                                     (event_id,owner,day)).fetchone()
                from .markdown_memory import read_reflection,reflection_document,write_private
                semantic=self.server.semantic
                memory_dir=semantic.markdown_path(owner).parent if semantic else None
                prior_path=memory_dir/f'REFLECTION-day-{day-1}.md' if memory_dir and day>1 else None
                prior_body=read_reflection(prior_path) if prior_path and prior_path.exists() else json.loads(prior[0]) if prior else None
                recalled=[]
                if self.server.semantic and capture:
                    recalled=self.server.semantic.search(self.server.sandbox.owner,owner,'Important interests, commitments, disagreements and questions from today')['results'][:4]
                identity=event.state['starting_identities'][owner]
                # Bound private identity independently of text size while preserving field labels.
                compact={key:value[:600] if isinstance(value,str) else value for key,value in identity.items()}
                payload={'day':day,'days':7,'starting_identity':compact,'sources':sources,
                         'retrieved_memories':[{'memory':r['memory'],'kind':r['kind']} for r in recalled],
                         'previous_reflection':prior_body,
                         'coverage':{'total_witnessed_messages':len(messages),'included':len(sources)}}
                if prior_body:
                    payload['previous_reflection']={'summary':prior_body['summary'][:600],**{k:[{**p,'text':p['text'][:300]} for p in prior_body[k][:2]] for k in CATEGORIES}}
                payload['retrieved_memories']=[{**n,'memory':n['memory'][:500]} for n in payload['retrieved_memories']]
                # The local service accepts 64 KiB requests. Unicode CVs and
                # accumulated reflections must not break a later bedtime.
                while len(json.dumps(payload,ensure_ascii=False).encode())>55000 and len(sources)>1:sources.pop(0)
                if len(json.dumps(payload,ensure_ascii=False).encode())>55000:
                    payload['starting_identity']={k:(v[:150] if isinstance(v,str) else v) for k,v in compact.items()}
                while len(json.dumps(payload,ensure_ascii=False).encode())>55000 and sources:sources.pop(0)
                payload['coverage']['included']=len(sources)
                result=validate_reflection(self.client.reflect(payload),sources) if capture else {'summary':'Conversation memory capture is disabled. No bedtime reflection was generated.',**{key:[] for key in CATEGORIES}}
                model='local qwen3-4b' if capture else 'capture_disabled'
                with self.lock:
                    if self.closed.is_set():return
                    with self.server.store.db() as db:
                        db.execute('INSERT INTO sleep_reflections VALUES(?,?,?,?,?,?,?)',
                            (event_id,day,owner,json.dumps(result),json.dumps(sources),model,time.time()))
                    if memory_dir:write_private(memory_dir/f'REFLECTION-day-{day}.md',reflection_document(day,result))
            with self.lock:
                self.state['phase']='completed' if day==7 else 'sleeping';self._save()
        except Exception as exc:
            with self.lock:
                if self.closed.is_set():return
                self.state['phase']='failed'
                self.state['error']=str(exc) if isinstance(exc,AppError) else 'Before-sleep reflection failed; no automatic retry'
                self._save()

    def next_day(self, actor):
        self.server.sandbox.authorize(actor)
        with self.lock:
            if self.state['phase']!='sleeping' or (self.thread and self.thread.is_alive()):
                raise AppError('Finish all three bedtime reflections before the next day',409)
            with self.server.store.db() as db:
                boundary=db.execute('SELECT coalesce(max(seq),0) FROM conversation_messages').fetchone()[0]
            previous=dict(self.state)
            self.state.update(day=self.state['day']+1,phase='awake',day_start_seq=boundary,error=None)
            try:result=self.server.event.start(actor,self.state['networking_settings'],continuation=True)
            except Exception:
                self.state=previous
                raise
            self._save()
            return result

    def close(self):
        self.closed.set()
        if self.thread and self.thread.is_alive():
            with self.lock:
                self.state['phase']='interrupted';self._save()

    def abort(self, actor):
        self.server.sandbox.authorize(actor)
        self.closed.set()
        self.server.event.stop(actor)
        with self.lock:
            self.state['phase']='interrupted'
            self.state['error']='Host stopped this seven-day test; pending reflection output is discarded'
            self._save()
        return self.server.event.status(actor)
