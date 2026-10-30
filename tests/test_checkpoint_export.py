import importlib.util,pathlib,tempfile,json,unittest
spec=importlib.util.spec_from_file_location('export_checkpoint',pathlib.Path(__file__).resolve().parents[1]/'scripts/export_checkpoint.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
class CheckpointTests(unittest.TestCase):
 def test_end_mechanisms(self):
  self.assertEqual(m.classify(True,[1],{'purpose':'wrap_up','decision':{}},None,3.7),'budget_wrap_up')
  self.assertEqual(m.classify(True,[1],{'purpose':'networking','decision':{'budget_choice':'end'}},None,4),'explicit_end')
  self.assertEqual(m.classify(True,[],None,None,100),'ended_before_run')
  self.assertEqual(m.classify(False,[1],{},'worker failed',100),'worker_error')
  self.assertEqual(m.classify(False,[],None,None,0),'budget_paused')
  self.assertEqual(m.classify(False,[1],{},None,10),'remaining_worker')
 def test_audit_wrapper_and_fences(self):
  with tempfile.TemporaryDirectory() as tmp:
   p=pathlib.Path(tmp)/'0001';p.mkdir();(p/'response.json').write_text(json.dumps({'at':123,'response':{'choices':[{'message':{'content':'```json\n{"budget_choice":"end","wait_seconds":0,"messages":[]}\n```'}}],'usage':{'total_tokens':4}}}))
   action,usage=m.read_decision(pathlib.Path(tmp),1);self.assertEqual(action['budget_choice'],'end');self.assertEqual(usage['total_tokens'],4)
if __name__=='__main__':unittest.main()
