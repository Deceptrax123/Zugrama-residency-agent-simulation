"""Private USD allowances, durable reservations and attributable token usage.

Amounts are integer microdollars. These are API-equivalent estimates, not cash
charges for the linked ChatGPT subscription. No cash payment occurs here; transfers only redistribute simulated allowance.
"""
import json
import threading
import time
import uuid
from decimal import Decimal, InvalidOperation

from .store import AppError

CALL_HOLD = 1_900_000
GUARD = 'residency-usd-v1'
RATES = {'input_per_million': 2, 'cached_input_per_million': .20, 'output_per_million': 12}
MODEL_RATES={'gpt-5.6-terra':RATES,
    'gpt-6.1-sol':{'input_per_million':2,'cached_input_per_million':.10,'output_per_million':10}}


def dollars(value):
    if isinstance(value, bool): raise AppError('Use a USD amount')
    try:
        amount = Decimal(str(value))
        if not amount.is_finite() or amount < 0 or amount > 10000 or amount.as_tuple().exponent < -2:
            raise InvalidOperation()
        return int(amount * 1000000)
    except (InvalidOperation, ValueError, TypeError):
        raise AppError('Use a USD amount from 0 to 10000 with at most two decimal places') from None


class AgentAccounts:
    def __init__(self, server):
        self.server = server
        self.lock = threading.RLock()
        with server.store.db() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS agent_wallets(owner_id TEXT PRIMARY KEY,limit_usd INTEGER,reserve_usd INTEGER,ended INTEGER DEFAULT 0);
                CREATE TABLE IF NOT EXISTS agent_usage(id TEXT PRIMARY KEY,owner_id TEXT,event_id TEXT,call_number INTEGER,purpose TEXT,status TEXT,hold_usd INTEGER,cost_usd INTEGER,input_tokens INTEGER,output_tokens INTEGER,total_tokens INTEGER,created_at REAL,links TEXT,request_ids TEXT);
                CREATE TABLE IF NOT EXISTS allowance_transfers(id TEXT PRIMARY KEY,event_id TEXT,from_owner TEXT,to_owner TEXT,amount_usd INTEGER CHECK(amount_usd>0),reason TEXT,conversation_id TEXT,workspace_id TEXT,call_number INTEGER,created_at REAL);
                CREATE INDEX IF NOT EXISTS allowance_transfers_event ON allowance_transfers(event_id,created_at);
                CREATE TABLE IF NOT EXISTS agent_requests(id TEXT PRIMARY KEY,owner_id TEXT,target_id TEXT,body TEXT,status TEXT,response TEXT,created_at REAL,event_id TEXT);
            ''')
            db.execute("UPDATE agent_usage SET status='unknown' WHERE status='pending'")

    def configure(self, actor, payload):
        self.server.sandbox.authorize(actor)
        if set(payload) != {'owner_id','limit_usd','reserve_usd'}: raise AppError('Provide an agent, USD limit and wrap-up reserve')
        owner = self.owner(payload['owner_id'])
        limit, reserve = dollars(payload['limit_usd']), dollars(payload['reserve_usd'])
        if reserve > limit: raise AppError('The wrap-up reserve must fit inside the allowance')
        with self.lock, self.server.store.db() as db:
            committed = db.execute("SELECT coalesce(sum(CASE WHEN status IN ('pending','unknown') THEN hold_usd ELSE cost_usd END),0) FROM agent_usage WHERE owner_id=?",(owner,)).fetchone()[0]
            net=db.execute('SELECT coalesce(sum(CASE WHEN to_owner=? THEN amount_usd ELSE 0 END),0)-coalesce(sum(CASE WHEN from_owner=? THEN amount_usd ELSE 0 END),0) FROM allowance_transfers',(owner,owner)).fetchone()[0]
            if limit+net < committed: raise AppError('The limit cannot be below spend plus pending or unresolved reservations',409)
            db.execute('INSERT INTO agent_wallets VALUES(?,?,?,0) ON CONFLICT(owner_id) DO UPDATE SET limit_usd=excluded.limit_usd,reserve_usd=excluded.reserve_usd,ended=0',(owner,limit,reserve))
        return self.view(actor)

    def owner(self, owner):
        from .identity import rows
        if not isinstance(owner,str) or owner not in {r['member_id'] for r in rows(self.server.store)}:
            raise AppError('Choose one of your saved agents')
        return owner

    def wallet(self, owner):
        with self.server.store.db() as db:return self._wallet(db,owner)

    def _wallet(self,db,owner):
        row=db.execute('SELECT * FROM agent_wallets WHERE owner_id=?',(owner,)).fetchone()
        if not row:return None
        totals=db.execute("SELECT coalesce(sum(cost_usd),0),coalesce(sum(CASE WHEN status IN ('pending','unknown') THEN hold_usd ELSE 0 END),0),coalesce(sum(input_tokens),0),coalesce(sum(output_tokens),0),coalesce(sum(total_tokens),0) FROM agent_usage WHERE owner_id=?",(owner,)).fetchone()
        given,received=db.execute('SELECT coalesce(sum(CASE WHEN from_owner=? THEN amount_usd ELSE 0 END),0),coalesce(sum(CASE WHEN to_owner=? THEN amount_usd ELSE 0 END),0) FROM allowance_transfers',(owner,owner)).fetchone()
        result=dict(row);result.update(per_call_reservation_usd=CALL_HOLD,base_limit_usd=row['limit_usd'],given_usd=given,received_usd=received,limit_usd=row['limit_usd']+received-given)
        result.update(spent_usd=totals[0],held_usd=totals[1],input_tokens=totals[2],output_tokens=totals[3],total_tokens=totals[4])
        result['remaining_usd']=max(0,result['limit_usd']-totals[0]-totals[1])
        result['protected_reserve_usd']=max(row['reserve_usd'],CALL_HOLD) if result['limit_usd']>=CALL_HOLD else row['reserve_usd']
        result['transferable_usd']=max(0,result['remaining_usd']-result['protected_reserve_usd'])
        result['state']='ended' if row['ended'] else 'paused' if result['remaining_usd']<CALL_HOLD else 'wrap_up' if result['remaining_usd']-CALL_HOLD<result['protected_reserve_usd'] else 'ready'
        return result

    def reserve(self, owner, event_id, call, request_ids):
        with self.lock:
            wallet = self.wallet(owner)
            if wallet is None: return None  # Existing unconfigured sandboxes retain their legacy behavior.
            if wallet['state'] in ('ended','paused'): return False
            self.server.hermes.check()
            health = self.server.hermes.request('/health',timeout=5)
            if health.get('residency_budget_guard') != GUARD:
                raise AppError('Restart the dedicated gateway with scripts/host.py to activate its budget guard; no inference was sent',503)
            entry = uuid.uuid4().hex
            purpose = 'wrap_up' if wallet['state']=='wrap_up' else 'networking'
            with self.server.store.db() as db:
                db.execute("INSERT INTO agent_usage VALUES(?,?,?,?,?,'pending',?,0,NULL,NULL,NULL,?,'[]',?)",(entry,owner,event_id,call,purpose,CALL_HOLD,time.time(),json.dumps(request_ids)))
            return {'id':entry,'purpose':purpose,'wallet':wallet}

    def settle(self, entry, response):
        if not entry: return
        usage = response.get('usage',{}) if isinstance(response,dict) else {}
        values = [usage.get(k) for k in ('prompt_tokens','completion_tokens','total_tokens')]
        valid = all(type(v) is int and v>=0 for v in values) and values[2]==values[0]+values[1] and values[2]>0
        # Cache savings are not exposed by this gateway's chat response. Value all
        # prompt tokens at the uncached rate; do not pretend to know actual billing.
        rates=MODEL_RATES.get(self.server.settings.hermes_model,RATES)
        cost = values[0]*rates['input_per_million']+values[1]*rates['output_per_million'] if valid else 0
        with self.lock, self.server.store.db() as db:
            db.execute("UPDATE agent_usage SET status=?,cost_usd=?,input_tokens=?,output_tokens=?,total_tokens=? WHERE id=? AND status='pending'",('recorded' if valid else 'unknown',cost,*(values if valid else (None,None,None)),entry['id']))

    def reject(self, entry):
        if entry:
            with self.server.store.db() as db:db.execute("UPDATE agent_usage SET status='rejected',hold_usd=0 WHERE id=? AND status='pending'",(entry['id'],))

    def unknown(self, entry):
        if entry:
            with self.server.store.db() as db: db.execute("UPDATE agent_usage SET status='unknown' WHERE id=? AND status='pending'",(entry['id'],))

    def link(self, entry, result):
        if entry:
            with self.server.store.db() as db:
                links=json.loads(db.execute('SELECT links FROM agent_usage WHERE id=?',(entry['id'],)).fetchone()[0])
                links.extend({'conversation_id':m['conversation_id'],'message_id':m['id'],'kind':'produced'} for m in result['messages'])
                db.execute('UPDATE agent_usage SET links=? WHERE id=?',(json.dumps(links),entry['id']))

    def context_links(self,entry,context):
        if entry:
            links=[{'conversation_id':m['conversation_id'],'message_id':m['id'],'kind':'context'} for m in context['recent_messages']]
            with self.server.store.db() as db:db.execute('UPDATE agent_usage SET links=? WHERE id=?',(json.dumps(links),entry['id']))

    def end(self, owner):
        with self.server.store.db() as db: db.execute('UPDATE agent_wallets SET ended=1 WHERE owner_id=?',(owner,))

    def requests(self, owner):
        with self.server.store.db() as db:
            return [dict(r) for r in db.execute("SELECT * FROM agent_requests WHERE owner_id=? AND status IN ('queued','considering','deferred') ORDER BY created_at LIMIT 20",(owner,))]

    def message(self, actor, payload):
        self.server.sandbox.authorize(actor)
        if set(payload)!={'owner_id','target_id','body'}: raise AppError('Choose your agent, a resident and a requirement')
        owner,target=self.owner(payload['owner_id']),self.owner(payload['target_id'])
        body=payload['body']
        if owner==target: raise AppError('Choose another resident as the target')
        if not isinstance(body,str) or not body.strip() or len(body)>4000 or '\x00' in body: raise AppError('Write a requirement of at most 4000 characters')
        with self.lock, self.server.store.db() as db:
            if len(self.requests(owner))>=20: raise AppError('This agent already has 20 open requests',409)
            event=self.server.event
            db.execute("INSERT INTO agent_requests VALUES(?,?,?,?,'queued','',?,?)",(uuid.uuid4().hex,owner,target,body.strip(),time.time(),event.state['event_id'] if event else None))
        if event:event.notify([owner])
        return self.view(actor)

    def updates(self, owner, updates):
        if not isinstance(updates,list) or len(updates)>20: raise AppError('Invalid request updates',502)
        allowed={r['id'] for r in self.requests(owner)}
        for item in updates:
            if (not isinstance(item,dict) or set(item)!={'id','status','response'} or item['id'] not in allowed or item['status'] not in ('considering','deferred','declined','addressed') or not isinstance(item['response'],str) or len(item['response'])>2000):
                raise AppError('Invalid private request update',502)
        return updates

    def apply_updates(self, owner, updates):
        with self.server.store.db() as db:
            for item in updates: db.execute('UPDATE agent_requests SET status=?,response=? WHERE id=? AND owner_id=?',(item['status'],item['response'],item['id'],owner))

    def view(self, actor):
        self.server.sandbox.authorize(actor)
        from .identity import rows
        agents=[]
        with self.server.store.db() as db:
            for row in rows(self.server.store):
                owner=row['member_id']
                usage=[{**dict(r),'links':json.loads(r['links']),'request_ids':json.loads(r['request_ids'])} for r in db.execute('SELECT * FROM agent_usage WHERE owner_id=? ORDER BY created_at DESC LIMIT 100',(owner,))]
                requests=[dict(r) for r in db.execute('SELECT * FROM agent_requests WHERE owner_id=? ORDER BY created_at DESC LIMIT 100',(owner,))]
                wallet=self.wallet(owner)
                if wallet:wallet={key:(value/1000000 if key.endswith('_usd') else value) for key,value in wallet.items()}
                for item in usage:
                    for key in ('cost_usd','hold_usd'):item[key]/=1000000
                agents.append({'owner_id':owner,'name':row['identity']['name'],'slot':row['slot'],'network_context':self.server.memory.policy(owner).get('network_context',False) if hasattr(self.server,'memory') else False,'wallet':wallet,'usage':usage,'requests':requests})
        return {'currency':'USD','basis':'estimated_api_equivalent','actual_provider_charge':None,'billing_note':'Linked ChatGPT usage is subscription-included; these are estimated API-equivalent dollars, not cash charges. Local memory compute and onboarding extraction are outside this networking allowance.','rates':MODEL_RATES.get(self.server.settings.hermes_model,RATES),'per_call_reservation_usd':CALL_HOLD/1000000,'agents':agents}
