"""Single-host signup and three human-authored agents in an isolated test database."""
import json
import secrets
import threading
import time
import uuid

from . import identity
from .event import HostEvent
from .npc import Facilitator
from .store import AppError


class IdentitySandbox:
    def __init__(self, server, agent_limit=3, minimum_agents=None):
        self.server = server
        self.agent_limit=agent_limit
        self.minimum_agents=minimum_agents or agent_limit
        self.lock = threading.RLock()
        identity.create_schema(server.store, agent_limit)
        from .budgets import AgentAccounts
        self.accounts = AgentAccounts(server)
        with server.store.db() as db:
            owner = db.execute('SELECT member_id FROM sandbox_owner WHERE singleton=1').fetchone()
        self.owner = owner[0] if owner else None
        self._configure_event()

    def signup(self, payload):
        with self.lock:
            if self.owner:
                raise AppError('This test already has a host. Sign in with the host account.', 409)
            token, csrf = self.server.store.register(payload)
            self.owner = self.server.store.authenticate(token)['member_id']
            with self.server.store.db() as db:
                db.execute('INSERT INTO sandbox_owner VALUES(1,?)', (self.owner,))
            return token, csrf

    def authorize(self, actor):
        if actor != self.owner:
            raise AppError('Only this test host can configure agent identities', 403)

    def _member(self, name, bio=''):
        token, _ = self.server.store.register({'name': name, 'email': uuid.uuid4().hex+'@agent.invalid',
            'password': secrets.token_urlsafe(36), 'join_code': self.server.settings.join_code, 'bio': bio})
        member = self.server.store.authenticate(token)['member_id']
        self.server.store.logout(token)
        return member

    def _configure_event(self):
        records = identity.rows(self.server.store)
        if len(records) < self.minimum_agents or not self.owner:
            return
        event = self.server.event
        if event and event.active:
            raise AppError('Stop the event and wait for pending calls before changing identities', 409)
        personas = {row['member_id']: row['identity'] for row in records}
        if event:
            event.personas = personas
            for member in personas:event.wakes.setdefault(member,threading.Event())
            return
        event = HostEvent(self.server, self.owner, personas, self.server.settings.data_dir/'host-event', host_is_observer=True, resident_limit=self.agent_limit)
        with self.server.store.db() as db:
            npc = db.execute("SELECT value FROM metadata WHERE key='sandbox_npc'").fetchone()
        npc_id = npc[0] if npc else self._member('Facilitator NPC', 'Disclosed test facilitator. Asks occasional questions about repeated agreement or concentrated attention; it only reads messages after joining.')
        if not npc:
            with self.server.store.db() as db:
                db.execute("INSERT INTO metadata VALUES('sandbox_npc',?)", (npc_id,))
            self.server.store.introduce(npc_id, {'body': 'I am the facilitator NPC. I join one conversation at a time and may ask a question when I witness repeated agreement or attention concentrating on one resident. I cannot see messages from before I joined.'})
        event.npc = Facilitator(event, npc_id)
        event.npc.enabled = event.state.get('npc_enabled', True)
        event.npc.questions = list(event.state.get('npc_questions', []))
        self.server.event = event

    def status(self, actor):
        self.authorize(actor)
        with self.server.store.db() as db:
            observations = [dict(row) for row in db.execute('SELECT * FROM compass_observations WHERE event_id=? ORDER BY id DESC LIMIT 100',
                (self.server.event.state['event_id'] if self.server.event else '',))]
        return {'enabled': True, 'owner_id': self.owner, 'ready': bool(self.server.event),
                'agents': identity.rows(self.server.store), 'agent_count': self.agent_limit,
                'compass_observations': observations,
                'cv_extraction_available': self.server.settings.hermes_model == 'gpt-5.6-terra',
                'identity_fields': [{'key': key, 'label': label, 'maximum': maximum,
                                     'question': identity.QUESTIONS.get(key),
                                     'choices': identity.CHOICES.get(key),
                                     'private': key in identity.PRIVATE}
                                    for key, (label, maximum) in identity.FIELDS.items()]}

    def extract_cv(self, actor, payload):
        self.authorize(actor)
        from .identity_extract import extract
        if set(payload) != {'cv'}: raise AppError('Provide only the CV for extraction')
        return extract(self.server.hermes,self.server.store.instance_id,actor,payload['cv'])

    def extract_pdf(self, actor, payload):
        self.authorize(actor)
        from .cv_pdf import pdf_text
        if set(payload) != {'pdf_base64'}: raise AppError('Provide one CV PDF')
        cv = pdf_text(payload['pdf_base64'])
        return self.extract_cv(actor, {'cv':cv})

    def extract_website(self,actor,payload):
        self.authorize(actor)
        from .website import fetch_page
        from .identity_extract import extract,validate_cv
        if set(payload)!={'url','cv'}:raise AppError('Provide a website URL and optional CV text')
        cv=payload['cv']
        if cv:validate_cv(cv)
        elif not isinstance(cv,str):raise AppError('CV context must be text')
        website=fetch_page(payload['url'])
        return extract(self.server.hermes,self.server.store.instance_id,actor,cv,website)

    def export_identity(self, actor, slot):
        self.authorize(actor)
        if slot not in tuple(str(n) for n in range(1,self.agent_limit+1)): raise AppError('Choose agent slot 1, 2, or 3')
        record = next((row for row in identity.rows(self.server.store) if row['slot'] == int(slot)), None)
        if not record: raise AppError('Save this agent before exporting its identity', 409)
        return {'filename': 'IDENTITY.md', 'markdown': record['identity_markdown'] or identity.markdown(record['identity'])}

    def review_identity(self, actor, payload):
        self.authorize(actor)
        from .identity_document import review
        return review(payload)

    def submit_identity(self, actor, payload):
        self.authorize(actor)
        if set(payload)-{'slot','markdown','cv_evidence','budget','memory_policy'} or not {'slot','markdown','cv_evidence'}<=set(payload):raise AppError('Submit the reviewed IDENTITY.md for an agent slot')
        if 'memory_policy' in payload:
            from .onboarding import memory_preferences
            memory_preferences(payload['memory_policy'])
        if 'budget' in payload:
            from .budgets import dollars
            budget=payload['budget']
            if not isinstance(budget,dict) or set(budget)!={'limit_usd','reserve_usd'}:raise AppError('Provide a USD allowance and wrap-up reserve')
            if dollars(budget['reserve_usd'])>dollars(budget['limit_usd']):raise AppError('The reserve must fit inside the allowance')
        result=self.review_identity(actor,{key:payload[key] for key in ('markdown','cv_evidence')})
        saved=self.save_agent(actor,payload['slot'],result['identity'],result['markdown'])
        if 'budget' in payload:
            member=next(r['member_id'] for r in saved['agents'] if r['slot']==payload['slot'])
            self.accounts.configure(actor,{'owner_id':member,**payload['budget']})
        if 'memory_policy' in payload:
            member=next(r['member_id'] for r in saved['agents'] if r['slot']==payload['slot'])
            self.server.memory.set_policy(member,payload['memory_policy'])
        return saved

    def save_agent(self, actor, slot, payload, identity_markdown=None):
        self.authorize(actor)
        if type(slot) is not int or not 1 <= slot <= self.agent_limit:
            raise AppError('Choose agent slot 1, 2, or 3')
        value = identity.validate_identity(payload)
        with self.lock:
            cycle=getattr(self.server,'cycle',None)
            if cycle and cycle.thread and cycle.thread.is_alive():
                raise AppError('Wait for before-sleep reflection before editing identities',409)
            event = self.server.event
            if event and (event.active or any(t.is_alive() for t in event.threads)):
                raise AppError('Stop the event and wait for pending calls before changing identities', 409)
            existing = next((row for row in identity.rows(self.server.store) if row['slot'] == slot), None)
            member = existing['member_id'] if existing else self._member(value['name'])
            self.server.store.update_profile(member, identity.profile(value))
            identity.save(self.server.store, slot, member, value, identity_markdown)
            # A fresh source ID records each authored introduction revision.
            with self.server.store.db() as db:
                db.execute('DELETE FROM introductions WHERE member_id=?', (member,))
            self.server.store.introduce(member, {'body': value['introduction']})
            self.server.capture_conversations([row['member_id'] for row in identity.rows(self.server.store)])
            self._configure_event()
            return self.status(actor)

    def start(self, actor, payload):
        self.authorize(actor)
        with self.lock:
            if not self.server.event:
                raise AppError('Save all three agent identities and their introductions before Start', 409)
            wallets=[self.accounts.wallet(owner) for owner in self.server.event.personas]
            if (self.server.settings.hermes_model=='gpt-5.6-terra' or any(wallet is not None for wallet in wallets)) and any(wallet is None for wallet in wallets):
                raise AppError('Set a USD allowance for each of the three agents in My agents before Start',409)
            cycle=getattr(self.server,'cycle',None)
            use_cycle=payload.get('seven_days',False)
            if type(use_cycle) is not bool:raise AppError('Seven-day mode must be true or false')
            if use_cycle:
                if not cycle:raise AppError('Start the local memory service to enable bedtime reflections',409)
                return cycle.start(actor,{key:value for key,value in payload.items() if key!='seven_days'})
            if cycle and cycle.thread and cycle.thread.is_alive():raise AppError('Bedtime reflection is still running',409)
            if 'seven_days' in payload:payload={key:value for key,value in payload.items() if key!='seven_days'}
            result=self.server.event.start(actor, payload)
            if cycle:
                cycle.state.update(enabled=False,phase='idle');cycle._save()
            return result

    def observe_compass(self, actor, payload):
        self.authorize(actor)
        event = self.server.event
        if not event or not event.state['event_id']:
            raise AppError('Start an event before recording observations', 409)
        if set(payload) != {'message_id', 'label', 'quote', 'note'}:
            raise AppError('Provide a source message, observation label, exact quote, and note')
        label = payload['label']
        if label not in ('alignment', 'tension', 'explicit_reconsideration', 'unclear'):
            raise AppError('Choose an observation label')
        quote = identity.text(payload['quote'], 'Evidence quote', 1200)
        note = identity.text(payload['note'], 'Observation', 2000)
        message_id = identity.text(payload['message_id'], 'Source message', 64)
        with event.lock:
            with self.server.store.db() as db:
                source = db.execute('SELECT * FROM conversation_messages WHERE id=?', (message_id,)).fetchone()
                if (not source or source['conversation_id'] not in event.rooms
                        or source['sender_id'] not in event.personas or quote not in source['body']):
                    raise AppError('Use an exact quotation from an agent message in this event')
                db.execute('INSERT INTO compass_observations(event_id,member_id,message_id,label,quote,note,recorded_at) VALUES(?,?,?,?,?,?,?)',
                    (event.state['event_id'], source['sender_id'], message_id, label, quote, note, time.time()))
        return self.status(actor)
