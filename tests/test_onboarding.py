import base64
import unittest
from residency.onboarding import prepare
from residency.identity_document import document
from residency.memory import default_policy
from residency.store import AppError
from tests.test_identity_sandbox import persona
from tests.pdf_fixture import make_pdf
from tests import test_identity_http as fixtures


def bundle():
    policy=default_policy()
    return {'schema':'dhun-residency-onboarding/v1','identity':{**persona(),'nickname':'River'},
            'markdown':document({**persona(),'nickname':'River'}),'budget':{'limit_usd':'12.00','reserve_usd':'2.25'},
            'memory':{key:policy[key] for key in ('instructions','exclude_terms','capture_conversations','recall_enabled')},
            'cv_pdf':{'name':'CV.pdf','base64':base64.b64encode(make_pdf()).decode()},'saved_at':'2026-10-26T00:00:00Z'}


class OnboardingTests(unittest.TestCase):
    def test_valid_export_prepares_review_and_local_pdf_text(self):
        saved=bundle();result=prepare({'bundle':saved})
        self.assertEqual(result['identity']['name'],'Agent One')
        self.assertEqual(result['identity']['nickname'],'River')
        self.assertEqual(result['budget'],saved['budget'])
        self.assertIn('Built Python tools',result['cv_text'])
        self.assertFalse(result['external_processing'])
        self.assertNotIn('Built Python tools',result['markdown'])
    def test_long_and_numerous_exclusions_survive_import(self):
        saved=bundle()
        saved['memory']['exclude_terms']=[('private detail ' * 50).strip()]+[f'private {i}' for i in range(30)]
        self.assertEqual(prepare({'bundle':saved})['memory_policy']['exclude_terms'],saved['memory']['exclude_terms'])

    def test_reject_bad_schema_money_memory_and_pdf(self):
        for bad in ({**bundle(),'schema':'other'},{**bundle(),'budget':{'limit_usd':'NaN','reserve_usd':'0'}},{**bundle(),'memory':{}},{**bundle(),'cv_pdf':{'name':'CV.pdf','base64':'invalid'}},{**bundle(),'markdown':'damaged'}):
            with self.assertRaises(AppError):prepare({'bundle':bad})


class OnboardingHTTPTests(unittest.TestCase):
    setUp=fixtures.IdentityHTTPTests.setUp
    def test_import_is_host_only_draft_without_models_and_final_submission_applies_preferences(self):
        payload={'bundle':bundle()}
        self.assertEqual(self.client.request('/api/sandbox/onboarding/import','POST',payload)[0],401)
        self.client.join()
        self.assertEqual(self.client.request('/api/sandbox/onboarding/import','POST',payload,{'X-CSRF-Token':'bad'})[0],403)
        code,draft,_=self.client.request('/api/sandbox/onboarding/import','POST',payload)
        self.assertEqual(code,200,draft);self.assertEqual(self.gateway.records,[])
        self.assertEqual(self.client.request('/api/state')[1]['sandbox']['agents'],[])
        draft['memory_policy']['instructions']='Remember music, commitments and differences of opinion.'
        draft['memory_policy']['exclude_terms']=[('do not keep this phrase ' * 30).strip()]+[f'private {i}' for i in range(30)]
        submission={key:draft[key] for key in ('markdown','budget','memory_policy')}
        submission.update(slot=1,cv_evidence=[])
        code,result,_=self.client.request('/api/sandbox/identity/submit','POST',submission)
        self.assertEqual(code,200,result)
        owner=result['agents'][0]['member_id']
        self.assertEqual(self.server.memory.policy(owner)['instructions'],draft['memory_policy']['instructions'])
        self.assertEqual(self.server.memory.policy(owner)['exclude_terms'],draft['memory_policy']['exclude_terms'])
        accounts=self.client.request('/api/agent-accounts')[1]
        self.assertEqual(accounts['agents'][0]['wallet']['limit_usd'],12)
        self.assertEqual(self.gateway.records,[])
        self.assertNotIn('Built Python tools',self.client.request('/api/state')[1]['sandbox']['agents'][0]['identity_markdown'])
