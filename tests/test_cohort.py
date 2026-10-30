import csv
from contextlib import contextmanager
import io
import json
from pathlib import Path
import threading
import time
import unittest

from residency.cohort import LiveCohort
from residency.identity import FIELDS,validate_identity
from residency.identity_document import document
from residency.local_mem0 import AgentMem0
from residency.sleep_cycle import SleepCycle
from residency.store import AppError
from tests.support import app,gateway,settings
from tests.test_integration import Client
from tests.test_identity_sandbox import persona
from tests.test_local_memory import FakeMemory


def export(count=4,explicit=False):
    result=[]
    for n in range(count):
        data={'identity':persona(f'Resident {n+1}'),'budget':{'limit_usd':'10.00','reserve_usd':'1.90'},
              'memory':{'instructions':'Remember interests, skills, commitments and disagreements.','exclude_terms':[],'capture_conversations':True,'recall_enabled':True}}
        if explicit:data['memory']['network_context']=False
        result.append({'user_id':f'anonymous:synthetic-{n}','status':'reviewed','data':json.dumps(data),'markdown':document(data['identity'])})
    return result


def import_payload(records=None,format='json',use=True):
    records=export() if records is None else records
    if format=='csv':
        stream=io.StringIO();writer=csv.DictWriter(stream,fieldnames=('user_id','status','data','markdown'));writer.writeheader();writer.writerows(records);raw=stream.getvalue()
    else:raw=json.dumps({'rows':records})
    return {'text':raw,'format':format,'use_memory_context':use}


@contextmanager
def fixture(limit=12):
    with gateway() as backend,settings(hermes_url=backend.url,hermes_key='synthetic-only',hermes_model='gpt-5.6-terra') as config,app(config) as server:
        backend.models=[{'id':'gpt-5.6-terra','root':'gpt-5.6-terra'}];backend.budget_guard='residency-usd-v1';backend.usage={'prompt_tokens':1000,'completion_tokens':100,'total_tokens':1100}
        server.sandbox=LiveCohort(server,limit)
        memory=FakeMemory();memory.health=lambda:{'status':'ready'}
        server.semantic=AgentMem0(server,memory);server.cycle=SleepCycle(server,memory)
        server.audit_directory=config.data_dir/'audit'
        client=Client(server.settings.public_origin);client.join('cohort-host@example.test','Cohort host')
        yield server,client,backend,memory


def apply(server,client,payload=None):
    payload=payload or import_payload();preview=server.sandbox.preview_import(server.sandbox.owner,payload)
    result=server.sandbox.apply_import(server.sandbox.owner,{'import':payload,'preview_hash':preview['preview_hash'],'confirmed':True})
    return result


def settle(event):
    for thread in event.threads:thread.join(10)
    if any(t.is_alive() for t in event.threads):raise AssertionError('Synthetic event did not drain')


class CohortTests(unittest.TestCase):
    def test_import_is_private_reviewed_previewed_idempotent_and_idle(self):
        with fixture() as (server,client,backend,memory):
            code,state,_=client.request('/api/state');self.assertIsNone(state['event']);self.assertEqual(state['sandbox']['agents'],[])
            raw=export(4,explicit=True)+[{'user_id':'draft','status':'draft'}];payload=import_payload(raw,format='csv');payload['text']='\ufeff'+payload['text']
            code,preview,_=client.request('/api/cohort/import/preview','POST',payload);self.assertEqual(code,200,preview);self.assertEqual(preview['skipped_drafts'],1)
            self.assertEqual(server.sandbox.status(server.sandbox.owner)['agents'],[]);self.assertEqual(backend.records,[])
            post={'import':payload,'preview_hash':preview['preview_hash'],'confirmed':True}
            self.assertEqual(client.request('/api/cohort/import/confirm','POST',post,{'X-CSRF-Token':'bad'})[0],403)
            self.assertEqual(client.request('/api/cohort/import/confirm','POST',{**post,'preview_hash':'wrong'})[0],409)
            code,result,_=client.request('/api/cohort/import/confirm','POST',post);self.assertEqual(code,200,result);self.assertEqual(len(result['imported_slots']),4)
            code,preview,_=client.request('/api/cohort/import/preview','POST',payload);self.assertTrue(all(r['action']=='unchanged' for r in preview['rows']))
            code,result,_=client.request('/api/cohort/import/confirm','POST',{'import':payload,'preview_hash':preview['preview_hash'],'confirmed':True});self.assertEqual(code,200,result);self.assertEqual(result['imported_slots'],[])
            self.assertEqual(len(server.event.personas),4);self.assertEqual(server.event.state['calls'],0);self.assertEqual(backend.records,[])
            self.assertTrue(all(not server.memory.policy(owner)['network_context'] for owner in server.event.personas))
            outsider=Client(server.settings.public_origin);self.assertEqual(outsider.request('/api/cohort/import/preview','POST',payload)[0],401)

    def test_invalid_rows_capacity_and_consent_have_no_partial_import(self):
        with fixture() as (server,client,backend,memory):
            bad_cases=[export(13),export(2)+[export(1)[0]],[{**export(1)[0],'markdown':'broken'}],[{**export(1)[0],'data':'invalid'}],[]]
            invalid=export(2);data=json.loads(invalid[1]['data']);data['budget']['limit_usd']='NaN';invalid[1]['data']=json.dumps(data);bad_cases.append(invalid)
            for records in bad_cases:
                with self.assertRaises(AppError):server.sandbox.preview_import(server.sandbox.owner,import_payload(records))
            self.assertEqual(server.sandbox.status(server.sandbox.owner)['agents'],[]);self.assertEqual(backend.records,[])
            apply(server,client,import_payload(export(2)))
            self.assertTrue(all(server.memory.policy(owner)['network_context'] for owner in server.event.personas))
            server.sandbox.start(server.sandbox.owner,{'max_calls':2,'npc_enabled':True,'seven_days':True})
            with self.assertRaises(AppError):server.sandbox.preview_import(server.sandbox.owner,import_payload())
            server.cycle.abort(server.sandbox.owner);settle(server.event)

    def test_full_four_resident_week_audit_and_individual_failure_isolation(self):
        with fixture() as (server,client,backend,memory):
            apply(server,client);people=list(server.event.personas)
            def reply(payload):
                ctx=json.loads(payload['messages'][-1]['content']);self.assertIn('private_memory',ctx)
                rooms=[r for r in ctx['conversations'] if r['joined']]
                action={'wait_seconds':0,'start_conversations':[],'join_conversations':[],'messages':[],'leave_conversations':[]}
                if rooms:action['messages']=[{'conversation_id':rooms[0]['id'],'body':'I enjoy exploring music, useful ideas and disagreements.'}]
                else:action['start_conversations']=[{'with':next(p for p in people if p!=ctx['member_id']),'body':'What are you interested in?'}]
                return json.dumps(action)
            backend.reply_factory=reply
            server.sandbox.start(server.sandbox.owner,{'max_calls':4,'npc_enabled':True,'seven_days':True})
            for day in range(1,8):
                settle(server.event);self.assertNotEqual(server.event.state['status'],'failed')
                server.cycle.before_sleep(server.sandbox.owner);server.cycle.thread.join(10)
                self.assertEqual(server.cycle.state['phase'],'completed' if day==7 else 'sleeping',server.cycle.state)
                self.assertEqual(len(server.cycle.view(server.sandbox.owner)['reflections']),4*day)
                if day<7:server.cycle.next_day(server.sandbox.owner)
            self.assertEqual(len(backend.records),28);self.assertEqual(len(list(server.audit_directory.glob('*/*/response.json'))),28)
            self.assertTrue(all(server.sandbox.accounts.wallet(p)['held_usd']==0 for p in people))
            seen=[json.loads(call['payload']['messages'][-1]['content']) for call in backend.records]
            self.assertTrue(any(c.get('previous_reflection') for c in seen[4:]))
            self.assertTrue(any(c.get('private_memory') for c in seen[4:]))
            # Every durable request/response pair must reconcile with the USD
            # ledger, including its resident, tokens and conversation links.
            with server.store.db() as db:
                usage={r['call_number']:dict(r) for r in db.execute('SELECT * FROM agent_usage WHERE event_id=?',(server.event.state['event_id'],))}
            self.assertEqual(set(usage),set(range(1,29)))
            requests=sorted(server.audit_directory.glob('*/*/request.json'))
            self.assertEqual(len(requests),28)
            for path in requests:
                request=json.loads(path.read_text());response=json.loads((path.parent/'response.json').read_text())['response']
                entry=usage[int(path.parent.name)];context=json.loads(request['payload']['messages'][-1]['content'])
                self.assertEqual(request['member_id'],entry['owner_id']);self.assertEqual(context['member_id'],entry['owner_id'])
                self.assertEqual(entry['status'],'recorded');self.assertEqual(entry['total_tokens'],response['usage']['total_tokens'])
                self.assertEqual(entry['input_tokens'],response['usage']['prompt_tokens']);self.assertEqual(entry['output_tokens'],response['usage']['completion_tokens'])
                links=json.loads(entry['links'])
                expected={(m['conversation_id'],m['id']) for m in context['recent_messages']}
                actual={(m['conversation_id'],m['message_id']) for m in links if m['kind']=='context'}
                self.assertEqual(actual,expected)
                self.assertEqual(path.stat().st_mode&0o777,0o600);self.assertEqual((path.parent/'response.json').stat().st_mode&0o777,0o600)
                self.assertNotIn('synthetic-only',path.read_text());self.assertNotIn('Authorization',request)
            # A single malformed agent pauses while other residents can continue.
            backend.reply_factory=lambda payload:'not JSON' if json.loads(payload['messages'][-1]['content'])['member_id']==people[0] else reply(payload)
            server.sandbox.start(server.sandbox.owner,{'max_calls':8,'npc_enabled':False})
            settle(server.event);self.assertEqual(server.event.state['status'],'completed_with_errors');self.assertIn(people[0],server.event.state['agent_errors']);self.assertGreater(server.event.state['completed_calls'],1)

    def test_failed_reservation_cannot_remove_another_workers_usage_entry(self):
        from unittest.mock import patch
        with fixture() as (server,client,backend,memory):
            apply(server,client,import_payload(export(2)));event=server.event;event.active=1;event.state['event_id']='synthetic-reservation-race'
            person=next(iter(event.personas));other_entry={'id':'another-worker-reservation'}
            def interrupted(owner,event_id,call,requests):
                # Reproduce a peer acquiring the same unconsumed call slot after
                # this worker's reservation fails, before its finally cleanup.
                event.account_entries[call]=other_entry
                raise AppError('Synthetic budget guard interruption',503)
            with patch.object(server.sandbox.accounts,'reserve',side_effect=interrupted):event._worker(person)
            self.assertIs(event.account_entries[1],other_entry);self.assertEqual(backend.records,[])

    def test_disabled_capture_does_not_send_conversations_to_bedtime_model(self):
        with fixture() as (server,client,backend,memory):
            apply(server,client,import_payload(export(2)));people=list(server.event.personas);a,b=people
            server.memory.set_policy(a,{'capture_conversations':False})
            def reply(payload):
                owner=json.loads(payload['messages'][-1]['content'])['member_id']
                return json.dumps({'wait_seconds':0,'start_conversations':[{'with':b if owner==a else a,'body':'PRIVATE-WITNESSED-SOURCE'}],'join_conversations':[],'messages':[],'leave_conversations':[]})
            backend.reply_factory=reply
            server.sandbox.start(server.sandbox.owner,{'max_calls':2,'npc_enabled':False,'seven_days':True});settle(server.event)
            server.cycle.before_sleep(server.sandbox.owner);server.cycle.thread.join(10)
            records=server.cycle.view(server.sandbox.owner)['reflections'];own=next(r for r in records if r['owner_id']==a)
            self.assertEqual(own['model'],'capture_disabled');self.assertEqual(own['sources'],[])
            self.assertEqual(len(memory.reflected),1);self.assertEqual(memory.reflected[0]['starting_identity']['name'],'Resident 2')
            self.assertIsNone(server.event.context(a)['previous_reflection'])

    def test_restart_preserves_unknown_holds_without_resuming_calls(self):
        from residency.budgets import AgentAccounts
        from residency.event import HostEvent
        with fixture() as (server,client,backend,memory):
            apply(server,client,import_payload(export(2)))
            owner=server.sandbox.owner;event=server.event;event.state.update(event_id='synthetic-restart',status='running',calls=1,max_calls=6)
            event._save();person=next(iter(event.personas))
            entry=server.sandbox.accounts.reserve(person,'synthetic-restart',1,[])
            server.cycle.state.update(enabled=True,day=1,phase='awake',event_id='synthetic-restart');server.cycle._save()
            restored=HostEvent(server,owner,event.personas,event.directory,host_is_observer=True,resident_limit=12)
            server.event=restored;server.sandbox.accounts=AgentAccounts(server);server.cycle=SleepCycle(server,memory)
            self.assertEqual(restored.state['status'],'interrupted');self.assertEqual(restored.active,0)
            self.assertEqual(server.cycle.state['phase'],'interrupted');self.assertEqual(backend.records,[])
            wallet=server.sandbox.accounts.wallet(person);self.assertEqual(wallet['held_usd'],1900000)
            with server.store.db() as db:self.assertEqual(db.execute('SELECT status FROM agent_usage WHERE id=?',(entry['id'],)).fetchone()[0],'unknown')

    def test_memory_opt_out_is_preserved_and_budget_update_below_spend_is_rejected(self):
        with fixture() as (server,client,backend,memory):
            records=export(2,explicit=True);payload=import_payload(records);apply(server,client,payload)
            owner=server.sandbox.owner;member=next(iter(server.event.personas))
            entry=server.sandbox.accounts.reserve(member,'synthetic-spend',1,[])
            server.sandbox.accounts.settle(entry,{'usage':{'prompt_tokens':1000,'completion_tokens':100,'total_tokens':1100}})
            draft=server.sandbox.status(owner)['agents'][0]
            server.sandbox.submit_identity(owner,{'slot':draft['slot'],'markdown':draft['identity_markdown'],'cv_evidence':[]})
            self.assertFalse(server.memory.policy(member)['network_context'])
            value=json.loads(records[0]['data']);value['budget']={'limit_usd':'0','reserve_usd':'0'};records[0]['data']=json.dumps(value)
            with self.assertRaises(AppError):server.sandbox.preview_import(owner,import_payload(records))
            code,_,_=client.request('/api/agent-memory/policy','POST',{'owner_id':member,'network_context':True});self.assertEqual(code,200)
            self.assertTrue(server.memory.policy(member)['network_context']);self.assertEqual(backend.records,[])

    def test_large_unicode_profiles_fit_guard_and_no_other_private_memory_is_visible(self):
        with fixture() as (server,client,backend,memory):
            records=export(12)
            for row in records:
                value=validate_identity(persona('Synthetic'))
                for key,(_,maximum) in FIELDS.items():value[key]='🌱'*maximum
                value['name']='Synthetic';value['introduction']='A synthetic introduction.'
                server.sandbox.save_agent(server.sandbox.owner,records.index(row)+1,value,document(value))
            event=server.event;event.state['event_id']='synthetic-context'
            for owner in event.personas:server.memory.set_policy(owner,{'network_context':True})
            people=list(event.personas);a,b,c=people[:3]
            result=server.store.conversation_action(a,{'start_conversations':[{'with':b,'body':'PRIVATE-A-B-ONLY useful idea'}]});event.rooms.update(result['created_conversations']);server.capture_conversations([a,b]);server.semantic.queue.join()
            own=event.context(a);other=event.context(c)
            self.assertIn('PRIVATE-A-B-ONLY',json.dumps(own));self.assertNotIn('PRIVATE-A-B-ONLY',json.dumps(other))
            self.assertLess(len(json.dumps(own,ensure_ascii=False).encode()),110000);self.assertTrue(own['coverage']['identity_text_clipped'])
            self.assertEqual(backend.records,[])
