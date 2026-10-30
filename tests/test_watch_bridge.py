import importlib.util,json,pathlib,sqlite3,tempfile,unittest
spec=importlib.util.spec_from_file_location('live_watch_bridge',pathlib.Path(__file__).resolve().parents[1]/'scripts/live_watch_bridge.py');mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
class WatchBridgeTests(unittest.TestCase):
 def test_capture_is_event_scoped_read_only_and_omits_private_columns(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=pathlib.Path(tmp);base=root/'.data/live-residency/state';(base/'host-event').mkdir(parents=True)
   state={'event_id':'current','status':'running','started_at':1,'completed_calls':2,'thinking':['a'],'conversation_ids':['current-room'],'starting_identities':{'a':{'name':'Ada','cv':'PRIVATE CV'},'b':{'name':'Bob','moral_compass':'PRIVATE VALUES'}}};(base/'host-event/state.json').write_text(json.dumps(state))
   db=sqlite3.connect(base/'residency.sqlite3');db.executescript('''CREATE TABLE members(id TEXT,name TEXT,email TEXT); CREATE TABLE conversation_messages(id TEXT,seq INTEGER,conversation_id TEXT,sender_id TEXT,body TEXT,created_at REAL);CREATE TABLE conversation_visits(conversation_id TEXT,member_id TEXT,joined_after_seq INTEGER,left_after_seq INTEGER,joined_at REAL DEFAULT 1,left_at REAL);CREATE TABLE agent_wallets(owner_id TEXT,ended INTEGER,limit_usd INTEGER);CREATE TABLE agent_tool_runs(event_id TEXT,owner_id TEXT,name TEXT,status TEXT,created_at REAL,result TEXT);CREATE TABLE private_memories(body TEXT);''')
   db.executemany('INSERT INTO members VALUES(?,?,?)',[('a','Ada','PRIVATE EMAIL'),('b','Bob','PRIVATE EMAIL')]);db.executemany('INSERT INTO conversation_messages VALUES(?,?,?,?,?,?)',[('old',1,'old-room','a','OLD EVENT PRIVATE',1),('m2',2,'current-room','a','Before Bob joined',2),('m3',3,'current-room','a','Visible to Bob',3),('m4',4,'current-room','a','After Bob left',4)]);db.executemany('INSERT INTO conversation_visits(conversation_id,member_id,joined_after_seq,left_after_seq) VALUES(?,?,?,?)',[('current-room','a',0,None),('current-room','b',2,3)]);db.execute("INSERT INTO agent_tool_runs VALUES('current','a','python_run','completed',3,'PRIVATE TOOL OUTPUT')");db.execute("INSERT INTO private_memories VALUES('PRIVATE MEMORY')");db.commit();db.close()
   state,messages=mod.capture(root);self.assertEqual([m['id'] for m in messages],['m2','m3','m4']);self.assertEqual([m['recipients'] for m in messages],[[],['b'],[]]);self.assertEqual(state['message_count'],3);self.assertEqual(state['directory'][0]['state'],'responding');self.assertNotIn('PRIVATE',json.dumps((state,messages)));db=sqlite3.connect(base/'residency.sqlite3');self.assertEqual(db.execute('select count(*) from conversation_messages').fetchone()[0],4);db.close()
if __name__=='__main__':unittest.main()

class MembershipTests(unittest.TestCase):
 def visit(self,member,start,end=None):return {'member_id':member,'joined_at':start,'left_at':end,'left_after_seq':None if end is None else int(end)}
 def test_replacements_do_not_look_like_a_three_person_group(self):
  visits=[self.visit('a',1),self.visit('b',1,3),self.visit('c',5)]
  r=mod.room_membership(visits,{'a','b','c'});self.assertEqual(r['peak_residents'],2);self.assertEqual(r['active_participants'],['a','c']);self.assertEqual(r['membership_change_count'],4)
 def test_actual_groups_and_facilitator_are_counted_separately(self):
  visits=[self.visit('a',1),self.visit('b',1),self.visit('npc',2),self.visit('c',3,4)]
  r=mod.room_membership(visits,{'a','b','c'});self.assertEqual(r['peak_residents'],3);self.assertEqual(r['active_participants'],['a','b','npc']);self.assertEqual(r['membership_changes'][-1]['kind'],'left')
 def test_long_membership_history_has_explicit_coverage(self):
  visits=[self.visit('a',i*2,i*2+1) for i in range(70)];r=mod.room_membership(visits,{'a'});self.assertEqual(len(r['membership_changes']),100);self.assertEqual(r['membership_change_count'],140);self.assertEqual(r['active_participants'],[]);self.assertEqual(r['peak_residents'],1)
