"""Host-reviewed import of Sites submissions into a fresh small-cohort residency."""
import csv
import hashlib
import io
import json
import time
from .sandbox import IdentitySandbox
from .identity import rows
from .identity_document import review
from .onboarding import memory_preferences
from .budgets import dollars
from .store import AppError,text
from .cohort_capacity import MAX_RESIDENTS,expand_capacity


class LiveCohort(IdentitySandbox):
    def __init__(self,server,limit=MAX_RESIDENTS):
        if server.event and server.event.active:raise AppError('Stop networking before changing capacity',409)
        expand_capacity(server.store,limit)
        super().__init__(server,agent_limit=limit,minimum_agents=2)
        with server.store.db() as db:
            db.execute('CREATE TABLE IF NOT EXISTS cohort_imports(source_id TEXT PRIMARY KEY,slot INTEGER UNIQUE,source_hash TEXT,imported_at REAL)')
            db.execute('CREATE TABLE IF NOT EXISTS cohort_enrollment_reviews(source_id TEXT PRIMARY KEY,reviewed_at REAL NOT NULL,data TEXT NOT NULL)')
        self.live_cohort=True
        if server.event and server.event.state['status']=='idle' and not server.event.state['event_id']:
            server.event.state['max_calls']=None;server.event._save()
        server.network_memory_enabled=True;server.bounded_context=True;server.resilient_events=True

    def status(self,actor):
        result=super().status(actor)
        return {**result,'live_cohort':True,'minimum_agents':2,'memory_context_enabled':True,'default_call_limit':None}

    def submit_identity(self,actor,payload):
        existing=any(r['slot']==payload.get('slot') for r in rows(self.server.store))
        result=super().submit_identity(actor,payload)
        if 'memory_policy' not in payload and not existing:
            member=next(r['member_id'] for r in result['agents'] if r['slot']==payload['slot'])
            self.server.memory.set_policy(member,{'network_context':True})
        return result

    def _idle(self):
        event=self.server.event;cycle=self.server.cycle
        if event and (event.active or any(t.is_alive() for t in event.threads)):raise AppError('Stop networking and wait for pending calls before importing',409)
        if cycle and (cycle.thread and cycle.thread.is_alive() or cycle.state['enabled'] and cycle.state['phase'] not in ('idle','completed','interrupted','failed')):raise AppError('Finish or stop the current day cycle before changing the cohort',409)
        if self.server.semantic and self.server.semantic.queue.unfinished_tasks:raise AppError('Wait for pending memory processing before importing',409)

    def preview_import(self,actor,payload):
        self.authorize(actor);self._idle()
        if not isinstance(payload,dict) or set(payload)!={'text','format','use_memory_context'} or type(payload['use_memory_context']) is not bool:raise AppError('Provide a JSON/CSV export and the memory-context choice')
        raw=payload['text']
        if not isinstance(raw,str) or len(raw.encode())>5*1024*1024:raise AppError('Choose an export below 5 MB')
        raw=raw.lstrip('\ufeff')
        try:
            if payload['format']=='csv':records=list(csv.DictReader(io.StringIO(raw)))
            elif payload['format']=='json':
                records=json.loads(raw)
                if isinstance(records,dict):records=records.get('rows',records.get('submissions',[records] if records.get('schema')=='dhun-residency-onboarding/v1' else None))
            else:raise AppError('Use a JSON or CSV export, rather than an executable SQL dump')
        except (ValueError,csv.Error):raise AppError('The export is not readable JSON/CSV') from None
        if not isinstance(records,list) or len(records)>500:raise AppError('Use an export with at most 500 submission rows')
        with self.server.store.db() as db:known={r['source_id']:dict(r) for r in db.execute('SELECT * FROM cohort_imports')}
        occupied={r['slot'] for r in rows(self.server.store)};seen=set();prepared=[];skipped=0
        for record in records:
            enrollment_review=None
            if not isinstance(record,dict):raise AppError('Each submission must be an object')
            if record.get('schema')=='dhun-residency-onboarding/v1':
                data=record;source_id='bundle:'+hashlib.sha256(record.get('markdown','').encode()).hexdigest()
            else:
                if record.get('status')=='draft' and 'host_review' in record:
                    approval=record['host_review']
                    if not isinstance(approval,dict) or set(approval)!={'approved','note'} or approval['approved'] is not True:raise AppError('Explicitly approve each draft and record why it is ready')
                    enrollment_review={'basis':'host_reviewed_draft','source_status':'draft',
                        'note':text(approval['note'],'Host review note',2000),'source_updated_at':text(record.get('updated_at'),'Source update time',100)}
                elif record.get('status')!='reviewed':skipped+=1;continue
                data=record.get('data')
                try:data=json.loads(data) if isinstance(data,str) else data
                except ValueError:raise AppError('A submission has invalid form JSON') from None
                source_id=record.get('user_id',record.get('userId'))
                if not isinstance(source_id,str) or not source_id or len(source_id)>256:raise AppError('Each reviewed row needs its source user_id')
            if source_id in seen:raise AppError('The export contains duplicate source user IDs')
            seen.add(source_id)
            if not isinstance(data,dict):raise AppError('A reviewed row is missing form data')
            draft=review({'identity':data.get('identity')}) if enrollment_review else review({'markdown':record.get('markdown'),'cv_evidence':[]})
            if enrollment_review:
                enrollment_review['source_data_hash']=hashlib.sha256(json.dumps(data,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
            budget=data.get('budget',{})
            if not isinstance(budget,dict) or set(budget)!={'limit_usd','reserve_usd'} or dollars(budget['reserve_usd'])>dollars(budget['limit_usd']):raise AppError('Check a participant USD allowance and reserve')
            policy=memory_preferences(data.get('memory'))
            # Respect explicit participant opt-outs. The host can authorize legacy
            # rows that predate this option, after inspecting the preview.
            policy.setdefault('network_context',False if enrollment_review else payload['use_memory_context'])
            source_hash=hashlib.sha256(json.dumps({'markdown':draft['markdown'],'budget':budget,'memory':policy},sort_keys=True).encode()).hexdigest()
            old=known.get(source_id)
            if old:slot=old['slot'];action='unchanged' if old['source_hash']==source_hash else 'update'
            else:
                available=sorted(set(range(1,self.agent_limit+1))-occupied)
                if not available:raise AppError(f'This deployment supports up to {self.agent_limit} residents')
                slot=available[0];occupied.add(slot);action='add'
            existing=next((r for r in rows(self.server.store) if r['slot']==slot),None)
            if existing:
                wallet=self.accounts.wallet(existing['member_id'])
                if wallet and dollars(budget['limit_usd'])<wallet['spent_usd']+wallet['held_usd']:raise AppError('An updated allowance is below recorded spend or unresolved holds')
            prepared.append({'source_id':source_id,'source_hash':source_hash,'slot':slot,'action':action,'identity':draft['identity'],'markdown':draft['markdown'],'budget':budget,'memory_policy':policy,
                **({'enrollment_review':enrollment_review} if enrollment_review else {})})
        if not prepared:raise AppError('No reviewed submissions or explicitly host-approved drafts were found')
        token=hashlib.sha256(json.dumps(prepared,sort_keys=True).encode()).hexdigest()
        return {'rows':prepared,'skipped_drafts':skipped,'preview_hash':token,'external_processing':False,'event_started':False}

    def apply_import(self,actor,payload):
        self.authorize(actor)
        if not isinstance(payload,dict) or set(payload)!={'import','preview_hash','confirmed'} or payload['confirmed'] is not True:raise AppError('Review and confirm the import first')
        with self.lock:
            preview=self.preview_import(actor,payload['import'])
            if payload['preview_hash']!=preview['preview_hash']:raise AppError('The cohort or import changed. Review it again before confirming',409)
            # Durable backup before the first mutation; preserve it on any partial
            # storage failure. No inference or Start is part of import.
            import sqlite3
            backup=self.server.settings.data_dir/('before-import-'+str(time.time_ns())+'.sqlite3')
            with self.server.store.db() as db,sqlite3.connect(backup) as destination:db.backup(destination)
            backup.chmod(0o600)
            applied=[]
            for record in preview['rows']:
                if record['action']=='unchanged':continue
                saved=self.save_agent(actor,record['slot'],record['identity'],record['markdown'])
                owner=next(r['member_id'] for r in saved['agents'] if r['slot']==record['slot'])
                self.accounts.configure(actor,{'owner_id':owner,**record['budget']})
                self.server.memory.set_policy(owner,record['memory_policy'])
                with self.server.store.db() as db:
                    db.execute('INSERT INTO cohort_imports VALUES(?,?,?,?) ON CONFLICT(source_id) DO UPDATE SET source_hash=excluded.source_hash,imported_at=excluded.imported_at',(record['source_id'],record['slot'],record['source_hash'],time.time()))
                    if record.get('enrollment_review'):
                        db.execute('INSERT INTO cohort_enrollment_reviews VALUES(?,?,?) ON CONFLICT(source_id) DO UPDATE SET reviewed_at=excluded.reviewed_at,data=excluded.data',(record['source_id'],time.time(),json.dumps(record['enrollment_review'])))
                applied.append(record['slot'])
            return {'imported_slots':applied,'skipped_drafts':preview['skipped_drafts'],'event_started':False,'model_calls':0}

    def start(self,actor,payload):
        self._idle()
        if not self.server.event:raise AppError('Import at least two reviewed participants before Start',409)
        self.server.hermes.check()
        if self.server.hermes.request('/health',timeout=5).get('residency_budget_guard')!='residency-usd-v1':raise AppError('The protected GPT gateway is unavailable; no inference was sent',503)
        self.server.semantic.client.health()
        return super().start(actor,payload)
