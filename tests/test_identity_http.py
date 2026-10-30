import json
import unittest
from dataclasses import replace
from unittest.mock import patch

from residency.config import APP_ROOT
from residency.sandbox import IdentitySandbox
from tests.support import account, app, gateway, settings
from tests.test_identity_sandbox import persona
from tests.test_integration import Client
from tests.test_host_event import silent


class IdentityHTTPTests(unittest.TestCase):
    def setUp(self):
        (APP_ROOT/'.data').mkdir(exist_ok=True)
        context = gateway()
        self.gateway = context.__enter__()
        self.addCleanup(context.__exit__, None, None, None)
        config_context = settings(hermes_url=self.gateway.url, hermes_key='test-key')
        config = config_context.__enter__()
        self.addCleanup(config_context.__exit__, None, None, None)
        app_context = app(config)
        self.server = app_context.__enter__()
        self.addCleanup(app_context.__exit__, None, None, None)
        self.server.sandbox = IdentitySandbox(self.server)
        self.client = Client(f'http://127.0.0.1:{self.server.server_port}')

    def test_signup_author_three_agents_then_explicit_start_via_fake_gateway(self):
        self.assertTrue(self.client.request('/api/setup')[1]['host_signup_available'])
        self.assertEqual(self.client.request('/api/sandbox/agents', 'POST', {})[0], 401)
        host = self.client.join('human@example.test', 'Test host')
        self.assertFalse(self.client.request('/api/setup')[1]['host_signup_available'])
        other = Client(self.client.base)
        self.assertEqual(other.request('/api/join', 'POST', account('other@example.test', 'Other'))[0], 409)
        payload = {'slot': 1, 'identity': persona('One')}
        self.assertEqual(self.client.request('/api/sandbox/agents', 'POST', payload, {'X-CSRF-Token': 'bad'})[0], 403)
        self.assertEqual(self.client.request('/api/event/start', 'POST', {'max_calls': 1})[0], 409)
        for slot in (1, 2, 3):
            self.assertEqual(self.client.request('/api/sandbox/agents', 'POST', {'slot': slot, 'identity': persona(f'Agent {slot}')})[0], 200)
        state = self.client.request('/api/state')[1]
        self.assertEqual(state['event']['status'], 'idle')
        self.assertEqual(state['event']['calls'], 0)
        self.assertNotIn(host, state['event']['participants'])
        self.assertEqual(self.gateway.records, [])
        self.assertEqual(self.client.request('/api/conversations/actions', 'POST', {'join_conversations': []})[0], 403)
        self.assertNotIn('PRIVATE-POLITICS', json.dumps(state['members']))
        self.gateway.reply = json.dumps(silent())
        self.assertEqual(self.client.request('/api/event/start', 'POST', {'max_calls': 1, 'npc_enabled': False})[0], 200)
        for thread in self.server.event.threads: thread.join(3)
        self.assertEqual(len(self.gateway.records), 1)
        context = json.loads(self.gateway.records[0]['payload']['messages'][-1]['content'])
        self.assertIn('PRIVATE-COMPASS', json.dumps(context['persona']))
        self.assertNotIn('PRIVATE-COMPASS', json.dumps(context['directory']))
        self.assertNotIn('starting_identities', context)
        graph = self.client.request('/api/event/graph?window=30')[1]
        self.assertEqual(len(graph['nodes']), 3)
        self.assertEqual(self.client.request('/api/event/graph?window=nan')[0], 400)
        self.assertEqual(self.client.request('/api/event/stop', 'POST', {})[0], 200)

    def test_nonhost_cannot_read_setup_identities_graph_or_private_audit(self):
        self.client.join()
        for slot in (1, 2, 3):
            self.client.request('/api/sandbox/agents', 'POST', {'slot': slot, 'identity': persona(str(slot))})
        # Synthetic internal login to verify defense even for an agent session.
        agent = next(iter(self.server.event.personas))
        token, csrf = self.server.store.new_session(agent)
        headers = {'Cookie': 'residency_session='+token, 'X-CSRF-Token': csrf}
        for path in ('/api/state', '/api/event/graph'):
            self.assertEqual(self.client.request(path, headers=headers)[0], 403)
        self.assertEqual(self.client.request('/api/sandbox/agents', 'POST', {'slot': 1, 'identity': persona()}, headers)[0], 403)
        event = self.client.request('/api/event', headers=headers)[1]
        self.assertEqual(event['feed'], [])
        self.assertEqual(event['npc']['questions'], [])

    def test_cv_extraction_is_host_only_gpt_preview_and_evidence_survives_save(self):
        from tests.test_identity_extraction import CV, CLAIM
        self.assertEqual(self.client.request('/api/sandbox/identity/extract','POST',{'cv':CV})[0],401)
        self.client.join()
        self.assertEqual(self.client.request('/api/sandbox/identity/extract','POST',{'cv':CV})[0],503)
        self.server.settings=replace(self.server.settings,hermes_model='gpt-5.6-terra')
        self.server.hermes.settings=self.server.settings
        self.gateway.models=[{'id':'gpt-5.6-terra','root':'gpt-5.6-terra'}]
        self.gateway.reply=json.dumps({'suggestions':[CLAIM]})
        code,result,_=self.client.request('/api/sandbox/identity/extract','POST',{'cv':CV})
        self.assertEqual(code,200);self.assertEqual(result['model'],'gpt-5.6-terra')
        self.assertTrue(result['external_processing'])
        self.assertEqual(self.client.request('/api/state')[1]['sandbox']['agents'],[])
        self.assertEqual(len(self.gateway.records),1)
        self.assertEqual(self.gateway.records[0]['payload']['model'],'gpt-5.6-terra')
        self.assertEqual(json.loads(self.gateway.records[0]['payload']['messages'][-1]['content'])['cv'],CV)
        self.assertEqual(self.client.request('/api/sandbox/identity/extract','POST',{'cv':''})[0],400)
        value={**persona(), 'cv':CV,'skills':'Python programming','cv_evidence':[CLAIM]}
        self.assertEqual(self.client.request('/api/sandbox/agents','POST',{'slot':1,'identity':value})[0],200)
        saved=self.client.request('/api/state')[1]['sandbox']['agents'][0]['identity']
        self.assertEqual(saved['cv_evidence'],[CLAIM])
        code,export,_=self.client.request('/api/sandbox/identity?slot=1')
        self.assertEqual(code,200);self.assertIn('## Skill identity',export['markdown'])
        self.assertIn(CLAIM['quote'],export['markdown'])
        self.assertEqual(self.client.request('/api/sandbox/identity?slot=2')[0],409)
        self.assertEqual(self.client.request('/api/sandbox/identity?slot=99')[0],400)
        agent=self.server.sandbox.status(self.server.sandbox.owner)['agents'][0]['member_id']
        token,csrf=self.server.store.new_session(agent)
        headers={'Cookie':'residency_session='+token,'X-CSRF-Token':csrf}
        self.assertEqual(self.client.request('/api/sandbox/identity?slot=1',headers=headers)[0],403)
        self.assertEqual(self.client.request('/api/sandbox/identity/extract','POST',{'cv':CV},headers)[0],403)
        self.assertEqual(len(self.gateway.records),1)
        self.gateway.reply=json.dumps({'suggestions':[{**CLAIM,'quote':'A model paraphrase rather than a verbatim quote'}]})
        self.assertEqual(self.client.request('/api/sandbox/identity/extract','POST',{'cv':CV})[0],200)
        self.assertEqual(self.client.request('/api/state')[1]['sandbox']['agents'][0]['identity'],saved)

    def test_pdf_upload_reads_text_then_calls_gpt_and_rejects_bad_uploads_before_inference(self):
        from tests.pdf_fixture import make_pdf
        from tests.test_cv_pdf import encoded
        from tests.test_identity_extraction import CLAIM
        payload={'pdf_base64':encoded(make_pdf())}
        route='/api/sandbox/identity/extract/pdf'
        self.assertEqual(self.client.request(route,'POST',payload)[0],401)
        self.client.join()
        self.server.settings=replace(self.server.settings,hermes_model='gpt-5.6-terra')
        self.server.hermes.settings=self.server.settings
        self.gateway.models=[{'id':'gpt-5.6-terra','root':'gpt-5.6-terra'}]
        optional_excerpt='Built Python tools\nfor water monitoring.'
        self.gateway.reply=json.dumps({'suggestions':[{**CLAIM,'quote':optional_excerpt},
            {'field':'project_background','text':'Worked on monitoring tools'}]})
        self.assertEqual(self.client.request(route,'POST',payload,{'X-CSRF-Token':'wrong'})[0],403)
        status,result,_=self.client.request(route,'POST',payload)
        self.assertEqual(status,200);self.assertIn(CLAIM['quote'],result['source_text'])
        self.assertNotIn(CLAIM['quote'],result['cv'])
        self.assertEqual(result['suggestions'][0]['quote'],optional_excerpt)
        self.assertEqual(result['suggestions'][1]['field'],'cv_notes')
        sent=json.loads(self.gateway.records[0]['payload']['messages'][-1]['content'])
        self.assertEqual(sent['cv'],result['source_text']);self.assertNotIn('pdf_base64',sent)
        self.assertEqual(self.client.request('/api/state')[1]['sandbox']['agents'],[])
        for value in ('bad base64',encoded(make_pdf(''))):
            self.assertIn(self.client.request(route,'POST',{'pdf_base64':value})[0],(400,422))
        self.assertEqual(len(self.gateway.records),1)

    def test_review_is_unsaved_and_edited_document_is_the_submitted_identity(self):
        from tests.test_identity_extraction import CV,CLAIM
        route='/api/sandbox/identity/review'
        self.assertEqual(self.client.request(route,'POST',{'identity':persona()})[0],401)
        self.client.join()
        initial={**persona(),'cv':CV,'skills':'Python programming','cv_evidence':[CLAIM]}
        status,preview,_=self.client.request(route,'POST',{'identity':initial})
        self.assertEqual(status,200)
        state=self.client.request('/api/state')[1]
        self.assertEqual(state['sandbox']['agents'],[]);self.assertEqual(state['introductions'],[])
        self.assertIsNone(self.server.event)
        edited=preview['markdown'].replace('Python programming','Reviewed human skill').replace('Listening and music','Music and shared meals')
        submission={'slot':1,'markdown':edited,'cv_evidence':[CLAIM]}
        self.assertEqual(self.client.request('/api/sandbox/identity/submit','POST',submission,{'X-CSRF-Token':'wrong'})[0],403)
        self.assertEqual(self.client.request('/api/sandbox/identity/submit','POST',{**submission,'markdown':'broken'})[0],400)
        self.assertEqual(self.client.request('/api/state')[1]['sandbox']['agents'],[])
        self.assertEqual(self.client.request('/api/sandbox/identity/submit','POST',submission)[0],200)
        record=self.client.request('/api/state')[1]['sandbox']['agents'][0]
        self.assertEqual(record['identity']['skills'],'Reviewed human skill')
        self.assertEqual(record['identity']['personal_offer'],'Music and shared meals')
        self.assertFalse(record['identity'].get('cv_evidence'))
        self.assertEqual(self.client.request('/api/sandbox/identity?slot=1')[1]['markdown'],record['identity_markdown'])
        self.assertIn('Reviewed human skill',record['identity_markdown'])
        with self.server.store.db() as db:
            revision=db.execute('SELECT identity_markdown FROM identity_revisions').fetchone()[0]
        self.assertEqual(revision,record['identity_markdown'])
        self.assertEqual(self.gateway.records,[])
        token,csrf=self.server.store.new_session(record['member_id'])
        headers={'Cookie':'residency_session='+token,'X-CSRF-Token':csrf}
        self.assertEqual(self.client.request(route,'POST',{'identity':initial},headers)[0],403)
        self.assertEqual(self.client.request('/api/sandbox/identity/submit','POST',submission,headers)[0],403)

    def test_website_extraction_highlights_expertise_products_and_offers_without_copying_raw_cv(self):
        route='/api/sandbox/identity/extract/website'
        self.client.join()
        self.server.settings=replace(self.server.settings,hermes_model='gpt-5.6-terra')
        self.server.hermes.settings=self.server.settings
        self.gateway.models=[{'id':'gpt-5.6-terra','root':'gpt-5.6-terra'}]
        website={'url':'https://portfolio.example/project','text':'Built Solar Atlas, a mapping product.','truncated':False}
        self.gateway.reply=json.dumps({'suggestions':[
            {'field':'subject_expertise','text':'Geospatial systems'},
            {'field':'products_built','text':'Solar Atlas: mapping tool; built the data pipeline'},
            {'field':'skills_offer_people','text':'Could offer mapping and data-pipeline development'},
        ]})
        with patch('residency.website.fetch_page',return_value=website) as fetch:
            status,result,_=self.client.request(route,'POST',{'url':website['url'],'cv':'Unrelated old job chronology.'})
        self.assertEqual(status,200);self.assertEqual(result['cv'],'')
        self.assertEqual(result['website'],website)
        self.assertEqual({row['field'] for row in result['suggestions']},{'subject_expertise','products_built','skills_offer_people'})
        context=json.loads(self.gateway.records[0]['payload']['messages'][-1]['content'])
        self.assertEqual(context['website']['text'],website['text'])
        self.assertEqual(self.client.request('/api/state')[1]['sandbox']['agents'],[])
        self.assertIn('Omit routine work chronology',self.gateway.records[0]['payload']['messages'][0]['content'])

    def test_personal_notes_are_listed_without_a_query_and_are_host_only(self):
        from residency.local_mem0 import AgentMem0
        from tests.test_local_memory import FakeMemory
        self.client.join()
        for slot in (1,2,3):self.client.request('/api/sandbox/agents','POST',{'slot':slot,'identity':persona(f'Agent {slot}')})
        event=self.server.event;event.state['event_id']='personal-notes-test'
        a,b,c=list(event.personas)
        memory=AgentMem0(self.server,FakeMemory());self.server.semantic=memory
        result=self.server.store.conversation_action(a,{'start_conversations':[{'with':b,'body':'A useful idea about music.'}]})
        event.rooms.add(result['created_conversations'][0]);self.server.capture_conversations([a,b]);memory.queue.join()
        status,notes,_=self.client.request('/api/agent-notes')
        self.assertEqual(status,200);self.assertEqual(len(notes['agents']),3)
        self.assertTrue(next(item for item in notes['agents'] if item['owner_id']==a)['notes'])
        self.assertFalse(next(item for item in notes['agents'] if item['owner_id']==c)['notes'])
        self.assertEqual(self.gateway.records,[])
        token,csrf=self.server.store.new_session(a)
        self.assertEqual(self.client.request('/api/agent-notes',headers={'Cookie':'residency_session='+token,'X-CSRF-Token':csrf})[0],403)


if __name__ == '__main__': unittest.main()
