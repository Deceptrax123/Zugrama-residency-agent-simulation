"""Local Sites integration fixture; all GPT, extraction and reflection are fake."""
import argparse
import json
from pathlib import Path
import signal
import sys
import threading
import time
import urllib.request

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from tests.test_cohort import fixture,apply,import_payload
from residency.site_bridge import SiteBridge
from residency.markdown_memory import write_private
from residency.agent_tools import AgentTools


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--records',required=True);parser.add_argument('--report',required=True);args=parser.parse_args()
    records=json.loads(Path(args.records).read_text());stop=threading.Event();signal.signal(signal.SIGTERM,lambda *_:stop.set());signal.signal(signal.SIGINT,lambda *_:stop.set())
    with fixture() as (server,client,backend,memory):
        apply(server,client,import_payload(records));people=list(server.event.personas);counts={}
        server.agent_tools=AgentTools(server,search=lambda query,limit:{'results':[{'url':'https://example.com','title':'Synthetic public source','excerpt':'Synthetic result; no network request'}]})
        def reply(payload):
            context=json.loads(payload['messages'][-1]['content']);owner=context['member_id'];index=people.index(owner)
            other_marker='PRIVATE-B-REQUEST' if index==0 else 'PRIVATE-A-REQUEST'
            if other_marker in json.dumps(context):raise AssertionError('Another resident private request entered model context')
            counts[owner]=counts.get(owner,0)+1
            action={'wait_seconds':0,'start_conversations':[], 'join_conversations':[],'messages':[],'leave_conversations':[]}
            if counts[owner]==1:
                action['start_conversations']=[{'with':next(p for p in people if p!=owner),'body':'A synthetic conversation about shared interests.'}]
                action['tool_calls']=[{'name':'python_run','arguments':{'code':'print(sum(range(10)))\nresult='+repr('PRIVATE-CODE-'+str(index))}},{'name':'web_search','arguments':{'query':'synthetic public source'}}]
            elif counts[owner]==2:
                if 'PRIVATE-CODE-'+str(index) not in json.dumps(context['tool_results']):raise AssertionError('Own code result was not retrieved')
                if 'PRIVATE-CODE-'+str(1-index) in json.dumps(context):raise AssertionError('Peer code leaked')
                room=next(r['id'] for r in context['conversations'] if r['joined'])
                action['tool_calls']=[{'name':'board_add','arguments':{'conversation_id':room,'title':'Synthetic shared board','text':'A witnessed calculation and diagram.','equations':['x^2+y^2=1',r'\href{javascript:alert(1)}{untrusted}'],'shapes':[{'type':'circle','x':500,'y':500,'r':200},{'type':'text','x':200,'y':250,'text':'<script>unsafe()</script>'}]}}]
            else:action['budget_choice']='end'
            return json.dumps(action)
        backend.reply_factory=reply
        path=server.settings.data_dir/'site-bridge.json';write_private(path,json.dumps({'origin':'https://zugrama-agent-residency.smudge0110.chatgpt.site','token':'synthetic-bridge-token-not-used-for-networking'}))
        def local_transport(payload):
            request=urllib.request.Request('http://127.0.0.1:5175/api/residency/bridge',data=json.dumps(payload,ensure_ascii=False).encode(),headers={'Content-Type':'application/json','Authorization':'Bearer qa-residency-bridge-only'})
            with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(request,timeout=20) as response:return json.load(response)
        bridge=SiteBridge(server,path,local_transport);bridge.tick();print('BRIDGE_FIXTURE_READY',flush=True)
        try:
            while not stop.is_set():
                bridge.tick()
                write_private(Path(args.report),json.dumps({'synthetic_only':True,'real_model_calls':0,'fake_model_calls':len(backend.records),'event_calls':server.event.state['calls'],'event_status':server.event.state['status'],'private_context_checks_passed':True}))
                stop.wait(.3)
        finally:bridge.close()


if __name__=='__main__':main()
