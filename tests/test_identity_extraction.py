import json
import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from residency.identity import CHOICES, QUESTIONS, markdown, public_identity, validate_identity
from residency.identity_extract import MODEL, SYSTEM, TARGETS, extract, validate_cv, validate_suggestions
from residency.store import AppError
from tests.test_identity_sandbox import persona

CV = 'Built Python tools for water monitoring. I offer Python mentoring to residents.'
CLAIM = {'field': 'skills', 'text': 'Python programming', 'quote': 'Built Python tools for water monitoring.'}


class IdentityExtractionTests(unittest.TestCase):
    def test_cv_evidence_retained_in_saved_identity_and_five_pillar_export(self):
        value = validate_identity({**persona(), 'cv': CV, 'skills': 'Python programming', 'cv_evidence': [CLAIM]})
        self.assertEqual(value['cv_evidence'], [CLAIM])
        self.assertNotIn('cv_evidence', public_identity(value))
        exported = markdown(value)
        for pillar in ('Name', 'Given identity', 'Skill identity', 'Contribution and reciprocity', 'Moral compass'):
            self.assertIn('## '+pillar, exported)
        self.assertIn(CLAIM['quote'], exported)
        self.assertIn('Share values with residents: no', exported)
        self.assertIn('PRIVATE-COMPASS', exported)  # Explicitly private host export.

    def test_general_cv_context_does_not_require_exact_quotes_or_fixed_categories(self):
        notes=validate_suggestions({'suggestions':[
            {'field':'skills','text':'Python programming','quote':'Built Python tools\nfor water monitoring.'},
            {'field':'professional_background','text':'Worked across disciplines'},
            {'field':'interests','text':'A longer description '*30,'confidence':'tentative'},
        ]},CV)
        self.assertEqual(notes[0]['quote'],'Built Python tools\nfor water monitoring.')
        self.assertEqual(notes[1],{'field':'cv_notes','text':'professional_background: Worked across disciplines','quote':''})
        self.assertEqual(len(notes),3)
        self.assertGreater(len(notes[2]['text']),300)
        self.assertEqual(len(validate_suggestions({'suggestions':[{'field':'skills','text':f'Note {i}'} for i in range(20)]},CV)),20)
        self.assertEqual(validate_suggestions({'skills':['Python','SQL']},CV)[0]['field'],'skills')
        self.assertEqual(validate_suggestions('A broad interpretation of the CV.',CV)[0]['field'],'cv_notes')
        for cv in ('', ' '*4, 'x'*16001, None):
            with self.assertRaises(AppError): validate_cv(cv)
        corrected=validate_identity({**persona(), 'cv': CV, 'skills': 'Unrelated skill', 'cv_evidence': [CLAIM]})
        self.assertFalse(corrected.get('cv_evidence'))
        self.assertEqual(validate_suggestions({'suggestions': []}, CV), [])

    def test_questions_cover_six_domains_without_invented_scores_or_cv_morality(self):
        for domain in ('care', 'equality', 'proportionality', 'loyalty', 'authority', 'sanctity'):
            self.assertIn('?', QUESTIONS['moral_'+domain])
            self.assertGreaterEqual(len(CHOICES['moral_'+domain]),4)
        self.assertIn('Qualifications alone are skills', SYSTEM)
        self.assertIn('moral values', SYSTEM)
        value = validate_identity({**persona(), 'moral_care': CHOICES['moral_care'][1]})
        self.assertEqual(value['moral_care'], CHOICES['moral_care'][1])

    def test_hermes_uses_terra_with_fresh_sessions_and_rejects_invalid_results_without_fallback(self):
        hermes=Mock();hermes.settings=SimpleNamespace(hermes_model=MODEL)
        choice={'finish_reason':'stop','message':{'content':json.dumps({'suggestions':[CLAIM]})}}
        hermes.request.return_value={'choices':[choice]}
        result=extract(hermes,'synthetic-app','host',CV)
        self.assertEqual(result['suggestions'],[CLAIM]);self.assertTrue(result['external_processing'])
        path,payload,headers=hermes.request.call_args.args
        self.assertEqual(path,'/v1/chat/completions');self.assertEqual(payload['model'],MODEL)
        self.assertEqual(json.loads(payload['messages'][-1]['content']),{'cv':CV,'target_fields':TARGETS})
        extract(hermes,'synthetic-app','host',CV)
        self.assertNotEqual(headers['X-Hermes-Session-Key'],hermes.request.call_args.args[2]['X-Hermes-Session-Key'])
        self.assertEqual(hermes.check.call_count,2)
        for response in ('A useful CV interpretation.', '```json\n'+json.dumps({'suggestions':[{'field':'skills','text':'Python'}]})+'\n```'):
            hermes.request.return_value={'choices':[{**choice,'message':{'content':response}}]}
            result=extract(hermes,'synthetic-app','host',CV)
            self.assertTrue(result['suggestions'])
        for invalid in ({**choice,'finish_reason':'length'}, {**choice,'message':{'content':''}}):
            hermes.request.return_value={'choices':[invalid]}
            before=hermes.request.call_count
            with self.assertRaises(AppError): extract(hermes,'synthetic-app','host',CV)
            self.assertEqual(hermes.request.call_count,before+1)
        hermes.settings.hermes_model='gpt-6.1-sol'
        before=hermes.request.call_count
        with self.assertRaises(AppError):extract(hermes,'synthetic-app','host',CV)
        self.assertEqual(hermes.request.call_count,before)


if __name__ == '__main__': unittest.main()
