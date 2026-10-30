import json,tempfile,unittest
from pathlib import Path
from residency.hermes import prepare_chat_payload
from residency.report_transport import request_coverage,check_answer_exposure,compact,field_exposure

class ReportTransportCoverageTests(unittest.TestCase):
    def test_corrected_answer_retains_original_citation_alias_mapping(self):
        with tempfile.TemporaryDirectory() as name:
            root=Path(name);directory=root/'task-correction';directory.mkdir();(root/'task').mkdir()
            (root/'task/citation-aliases.json').write_text(json.dumps({'s1':'original'}))
            (directory/'request.json').write_text(json.dumps({'messages':[{'role':'user','content':compact({'messages':[{'id':'s1','body':'A witnessed source'}]})}]}))
            coverage=check_answer_exposure(directory,[{'evidence':[{'message_id':'original','quote':'witnessed source'}]}])
            self.assertTrue(coverage['input_values_preserved'])
    def test_top_level_coverage_handles_original_noncompact_unicode_json(self):
        text=json.dumps({'early':'clé','private_memory':{'body':'quoted "value"'},'late':'tail'},ensure_ascii=False)
        start=text.index('{',1);self.assertEqual(field_exposure(text,'private_memory',text[:start]),'absent')
        self.assertEqual(field_exposure(text,'private_memory',text[:start+8]),'partial')
        self.assertEqual(field_exposure(text,'private_memory',text),'full')
    def test_native_cap_is_distinct_from_saved_context_and_quotes_need_visible_sources(self):
        with tempfile.TemporaryDirectory() as name:
            directory=Path(name);source={'id':'late','body':'TAIL EVIDENCE'}
            context={'padding':['x'*1000 for _ in range(70)],'messages':[source],'reference_guide':{'sections':['guide']}}
            payload={'messages':[{'role':'user','content':compact(context)}]}
            (directory/'request.json').write_text(json.dumps(payload))
            coverage=request_coverage(directory)
            self.assertEqual(coverage['message_exposure']['absent'],1)
            self.assertEqual(coverage['reference_guide'],'absent')
            answer=[{'evidence':[{'message_id':'late','quote':'TAIL EVIDENCE'}]}]
            with self.assertRaises(ValueError):check_answer_exposure(directory,answer)
            wire,metadata=prepare_chat_payload(payload);self.assertTrue(metadata)
            (directory/'wire-request.json').write_text(json.dumps(wire))
            coverage=check_answer_exposure(directory,answer)
            self.assertEqual(coverage['message_exposure']['full'],1)
            self.assertEqual(coverage['reference_guide'],'full')
            self.assertTrue(coverage['input_values_preserved'])
