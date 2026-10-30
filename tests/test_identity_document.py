import unittest

from residency.identity import validate_identity
from residency.identity_document import document,parse,review
from residency.store import AppError
from tests.test_identity_sandbox import persona
from tests.test_identity_extraction import CV,CLAIM


class IdentityDocumentTests(unittest.TestCase):
    def test_nickname_round_trip_and_documents_saved_before_nickname(self):
        value=validate_identity({**persona(),'nickname':'River'})
        self.assertEqual(parse(document(value))['nickname'],'River')
        old=document(value).replace('### Nickname\n\n```text\nRiver\n```\n\n','')
        self.assertEqual(parse(old)['nickname'],'')

    def test_five_pillars_round_trip_including_introduction_disclosure_and_embedded_markdown(self):
        value=validate_identity({**persona(),'cv':'## Given identity\n```text\nNationalities are not inferred.\n```\nUnicode: नमस्ते',
                                 'share_values':True,'skills':'Python\nCode review'})
        rendered=document(value)
        self.assertEqual(validate_identity(parse(rendered)),value)
        self.assertIn('## Public introduction',rendered)
        self.assertIn('## Moral compass',rendered)
        old=rendered.replace('### Other relevant project context\n\n```text\n\n```\n\n','')
        self.assertEqual(validate_identity(parse(old)),value)

    def test_edited_file_updates_fields_and_drops_stale_extraction_evidence(self):
        initial=review({'identity':{**persona(),'cv':CV,'skills':'Python programming','cv_evidence':[CLAIM]}})
        edited=initial['markdown'].replace('Python programming','Human-corrected skill')
        result=review({'markdown':edited,'cv_evidence':[CLAIM]})
        self.assertEqual(result['identity']['skills'],'Human-corrected skill')
        self.assertFalse(result['identity'].get('cv_evidence'))
        self.assertIn('Human-corrected skill',result['markdown'])
        self.assertNotIn('Python programming',result['markdown'])

    def test_reject_broken_structure_missing_required_fields_and_invalid_disclosure(self):
        raw=document(validate_identity(persona()))
        for invalid in (raw.replace('## Skill identity','## Hidden identity'),
                        raw.replace('Agent One',''),raw+'\nUnexpected text',
                        raw.rsplit('```',1)[0],raw.replace('```text\nno\n```','```text\nmaybe\n```')):
            with self.assertRaises(AppError):review({'markdown':invalid,'cv_evidence':[]})
