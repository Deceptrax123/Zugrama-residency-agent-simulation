import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
from residency.identity_extract import MODEL
from residency.intake_extractor import IntakeClient, IntakeExtractor
from residency.store import AppError


class IntakeExtractorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.client, self.hermes = Mock(), Mock()
        self.hermes.settings = SimpleNamespace(hermes_model=MODEL)
        self.job = {'id':'synthetic-job','lease_token':'lease','pdf_base64':'synthetic','model':MODEL}
        self.client.post.return_value = {'job':self.job}
        self.worker = IntakeExtractor(self.client, self.hermes, Path(self.temp.name)/'journal.sqlite3')
        self.addCleanup(self.worker.db.close)

    @patch('residency.intake_extractor.extract')
    @patch('residency.intake_extractor.pdf_text', return_value='CV only')
    def test_only_cv_suggestions_are_returned_and_jobs_are_not_replayed(self, pdf, extract):
        extract.return_value = {'model':MODEL,'suggestions':[{'field':'skills','text':'Mapping','quote':''}], 'source_text':'private source'}
        self.assertEqual(self.worker.step(),'completed')
        extract.assert_called_once_with(self.hermes,'zugrama-onboarding','synthetic-job','CV only')
        result=self.client.post.call_args.args[1]
        self.assertEqual(set(result),{'id','lease_token','status','result'})
        self.assertEqual(set(result['result']),{'model','suggestions'})
        self.assertEqual(self.worker.step(),'failed')
        self.assertEqual(extract.call_count,1)
        self.assertIn('already attempted',self.client.post.call_args.args[1]['error'])

    @patch('residency.intake_extractor.extract')
    @patch('residency.intake_extractor.pdf_text')
    def test_wrong_model_and_invalid_pdf_never_call_inference(self,pdf,extract):
        self.job['model']='different-model'
        self.assertEqual(self.worker.step(),'failed');pdf.assert_not_called();extract.assert_not_called()
        self.job['model']=MODEL;pdf.side_effect=AppError('Unreadable scanned PDF')
        self.assertEqual(self.worker.step(),'failed');extract.assert_not_called()
        self.assertEqual(self.client.post.call_args.args[1]['error'],'Unreadable scanned PDF')

    @patch('residency.intake_extractor.extract')
    @patch('residency.intake_extractor.pdf_text',return_value='CV')
    def test_failed_delivery_does_not_repeat_model_and_daily_limit_is_enforced(self,pdf,extract):
        extract.return_value={'model':MODEL,'suggestions':[]}
        def request(path,payload):
            if path.endswith('claim'):return {'job':self.job}
            raise OSError('Synthetic delivery failure')
        self.client.post.side_effect=request
        with self.assertRaises(OSError):self.worker.step()
        self.client.post.side_effect=None
        self.assertEqual(self.worker.step(),'failed');self.assertEqual(extract.call_count,1)
        self.job['id']='second-job';self.worker.daily_limit=1
        self.assertEqual(self.worker.step(),'failed');self.assertEqual(extract.call_count,1)
        self.assertIn('daily',self.client.post.call_args.args[1]['error'])

    def test_idle_and_origin_scope(self):
        self.client.post.return_value={'job':None}
        self.assertEqual(self.worker.step(),'idle')
        for origin in ('http://zugrama-agent-residency.smudge0110.chatgpt.site','https://other.example','https://zugrama-agent-residency.smudge0110.chatgpt.site/redirect'):
            with self.assertRaises(ValueError):IntakeClient(origin,'secret')
