import json
from pathlib import Path
import threading
import unittest
from unittest.mock import Mock,patch

from residency.agent_tools import AgentTools,board_content
from residency.code_sandbox import execute
from residency.site_bridge import SiteBridge
from residency.store import AppError
from tests.test_cohort import fixture,apply,export,import_payload,settle
from tests import test_site_bridge


def call(name,**arguments):return {'name':name,'arguments':arguments}


class CodeSandboxTests(unittest.TestCase):
    def test_real_standard_library_calculation_and_clean_environment(self):
        value=execute('import os\nprint(sum(range(10)))\nresult={"root":math.sqrt(81),"env":dict(os.environ)}')
        self.assertTrue(value['ok'],value);self.assertEqual(value['stdout'],'45\n');self.assertEqual(value['result']['root'],9)
        self.assertNotIn('OPENAI_API_KEY',value['result']['env']);self.assertNotIn('HERMES_HOME',value['result']['env'])

    def test_no_host_reads_writes_network_children_or_privilege_changes(self):
        operations=["open('/etc/passwd').read()","open('/tmp/zugrama-sandbox-escape','w').write('escape')",
            "import os\nos.fork()","import os\nos.system('echo should-not-run')",
            "import resource\nresource.setrlimit(resource.RLIMIT_CPU,(100,100))"]
        for code in operations:
            with self.subTest(code=code):
                value=execute(code)
                # os.system can report a denied child creation as a return code.
                if 'os.system' not in code:self.assertFalse(value['ok'],value)
                self.assertNotIn('should-not-run',value.get('stdout',''))
        self.assertFalse(Path('/tmp/zugrama-sandbox-escape').exists())
        for operation in ('socket(2,1,0)','prctl(38,0,0,0,0)'):
            value=execute('import ctypes\nlibc=ctypes.CDLL(None,use_errno=True)\nresult=[libc.'+operation+',ctypes.get_errno()]')
            self.assertTrue(value['ok'],value);self.assertEqual(value['result'],[-1,1])

    def test_cpu_memory_output_and_nonfinite_result_fail_boundedly(self):
        for code in ('while True: pass','result=bytearray(400*1024*1024)','result=float("nan")',
                     'import sys\nsys.__stdout__.write("x"*1000000)'):
            with self.subTest(code=code):self.assertFalse(execute(code)['ok'])
        value=execute('print("x"*20000)');self.assertTrue(value['ok']);self.assertTrue(value['truncated']);self.assertEqual(len(value['stdout']),8000)
        with self.assertRaises(ValueError):execute('x'*16001)


class AgentToolTests(unittest.TestCase):
    def prepare(self,server):
        apply(server,None,import_payload(export(3)));server.agent_tools=AgentTools(server,search=Mock(return_value={'results':[{'url':'https://example.com','excerpt':'PUBLIC-SEARCH'}]}))
        event=server.event;event.state.update(event_id='synthetic-tools',status='running')
        return event,list(event.personas),server.agent_tools

    def test_private_receipts_idempotence_and_restart(self):
        with fixture() as (server,client,backend,memory):
            event,(a,b,c),tools=self.prepare(server)
            tools.run(a,1,[call('python_run',code="result='PRIVATE-TOOL-A'")]);tools.run(a,1,[call('python_run',code="result='MUST-NOT-REPLAY'")])
            self.assertEqual(len(tools.history(a)),1);self.assertIn('PRIVATE-TOOL-A',json.dumps(tools.context(a)));self.assertNotIn('PRIVATE-TOOL-A',json.dumps(tools.context(b)))
            paths=list((server.settings.data_dir/'agent-tools').glob('*/*/*.json'));self.assertEqual(len(paths),1);self.assertEqual(paths[0].stat().st_mode&0o777,0o600)
            with server.store.db() as db:db.execute("INSERT INTO agent_tool_runs VALUES('interrupted',?,?,?,?,?,NULL,'started',0,NULL)",(event.state['event_id'],a,2,'python_run','{}'))
            restored=AgentTools(server);self.assertEqual(next(r for r in restored.history(a) if r['id']=='interrupted')['status'],'interrupted')
            self.assertEqual(backend.records,[])

    def test_board_visibility_follows_join_and_leave_periods_in_context_and_site(self):
        with fixture() as (server,client,backend,memory):
            event,(a,b,c),tools=self.prepare(server)
            room=server.store.conversation_action(a,{'start_conversations':[{'with':b,'body':'Opening'}]})['created_conversations'][0];event.rooms.add(room)
            tools.run(a,1,[call('board_add',conversation_id=room,title='BEFORE-C',text='First draft',equations=['x^2+y^2=1'],shapes=[{'type':'circle','x':500,'y':500,'r':200}])])
            self.assertEqual(len(tools.boards(b)),1);self.assertEqual(tools.boards(c),[])
            server.store.conversation_action(c,{'join_conversations':[room]})
            server.store.conversation_action(a,{'leave_conversations':[room]})
            tools.run(b,2,[call('board_add',conversation_id=room,title='DURING-A-GAP',text='Second draft')])
            server.store.conversation_action(a,{'join_conversations':[room]})
            tools.run(b,3,[call('board_add',conversation_id=room,title='AFTER-REJOIN',text='Third draft')])
            self.assertEqual({r['title'] for r in tools.boards(a)},{'BEFORE-C','AFTER-REJOIN'})
            self.assertEqual({r['title'] for r in tools.boards(c)},{'DURING-A-GAP','AFTER-REJOIN'})
            self.assertEqual(len(tools.boards()),3);self.assertEqual(event.state['message_count'],3)
            bridge=test_site_bridge.SiteBridgeTests().bridge(server);views={r['owner_id']:r['data'] for r in bridge.snapshots()}
            self.assertNotIn('BEFORE-C',json.dumps(views['anonymous:synthetic-2']))
            self.assertNotIn('DURING-A-GAP',json.dumps(views['anonymous:synthetic-0']))
            self.assertEqual(len(views['host']['boards']),3)

    def test_invalid_arguments_unauthorized_boards_and_failures_are_recorded(self):
        with fixture() as (server,client,backend,memory):
            event,(a,b,c),tools=self.prepare(server)
            room=server.store.conversation_action(a,{'start_conversations':[{'with':b,'body':'Opening'}]})['created_conversations'][0];event.rooms.add(room)
            tools.run(c,1,[call('board_add',conversation_id=room,title='FORBIDDEN',text='Not joined'),call('python_run',code="open('/etc/passwd').read()"),call('web_search',query='query',owner_id=a)])
            self.assertTrue(all(r['status']=='failed' for r in tools.history(c)));self.assertEqual(tools.boards(),[]);tools.search.assert_not_called()
            for item in ([call('shell',code='ls')],[call('web_search',query='q')]*4,{'bad':True}):
                with self.assertRaises(AppError):tools.validate(item)
            for shape in ({'type':'script','x':0,'y':0},{'type':'line','x':0,'y':0,'x2':float('nan'),'y2':10}):
                with self.assertRaises(AppError):board_content({'title':'Invalid','shapes':[shape]})

    def test_model_uses_own_tool_results_next_turn_without_hidden_calls(self):
        with fixture() as (server,client,backend,memory):
            apply(server,client,import_payload(export(2)));server.agent_tools=AgentTools(server,search=Mock(return_value={'results':[]}));counts={}
            def reply(payload):
                ctx=json.loads(payload['messages'][-1]['content']);owner=ctx['member_id'];counts[owner]=counts.get(owner,0)+1
                self.assertIn('tool_calls',payload['messages'][0]['content']);self.assertIn('tool_access',ctx)
                action={'wait_seconds':0,'start_conversations':[],'join_conversations':[],'messages':[],'leave_conversations':[]}
                if counts[owner]==1:action['tool_calls']=[call('python_run',code='result='+repr('PRIVATE-'+owner))]
                else:
                    self.assertIn('PRIVATE-'+owner,json.dumps(ctx['tool_results']))
                    for peer in server.event.personas:
                        if peer!=owner:self.assertNotIn('PRIVATE-'+peer,json.dumps(ctx))
                    action['budget_choice']='end'
                return json.dumps(action)
            backend.reply_factory=reply
            server.sandbox.start(server.sandbox.owner,{'npc_enabled':False});settle(server.event)
            self.assertEqual(server.event.state['status'],'completed',server.event.state);self.assertEqual(len(backend.records),4)
            self.assertEqual(len(server.agent_tools.history()),2);self.assertEqual(len(list(server.audit_directory.glob('*/*/request.json'))),4)
            with server.store.db() as db:
                self.assertEqual(db.execute("SELECT count(*) FROM agent_usage WHERE status='recorded'").fetchone()[0],4)
                linked=[link for r in db.execute('SELECT links FROM agent_usage') for link in json.loads(r[0]) if link['kind']=='tool']
                self.assertEqual(len(linked),2)

    def test_final_bounded_call_executes_tools_and_stop_skips_pending_tools(self):
        with fixture() as (server,client,backend,memory):
            apply(server,client,import_payload(export(2)));server.agent_tools=AgentTools(server)
            backend.reply_factory=lambda payload:json.dumps({'wait_seconds':0,'start_conversations':[],'join_conversations':[],'messages':[],'leave_conversations':[],'tool_calls':[call('python_run',code='result=42')]})
            server.sandbox.start(server.sandbox.owner,{'max_calls':1,'npc_enabled':False});settle(server.event)
            self.assertEqual(server.agent_tools.history()[0]['result']['data']['result'],42)
            server.event.state['status']='stopping';server.agent_tools.run(next(iter(server.event.personas)),2,[call('python_run',code='result=99')])
            self.assertEqual(len(server.agent_tools.history()),1)

    def test_large_results_and_snapshot_stay_bounded(self):
        with fixture() as (server,client,backend,memory):
            event,(a,b,c),tools=self.prepare(server);tools.code=lambda code:{'ok':True,'result':'界'*7000}
            for number in range(4):tools.run(a,number,[call('python_run',code='large synthetic result')])
            context=tools.context(a);self.assertLess(len(json.dumps(context,ensure_ascii=False).encode()),16000)
            view=SiteBridge.bounded({'tool_runs':tools.history()*10,'boards':[]},50000)
            self.assertLessEqual(len(json.dumps(view,ensure_ascii=False).encode()),50000);self.assertTrue(view['coverage']['trimmed'])


if __name__=='__main__':unittest.main()
