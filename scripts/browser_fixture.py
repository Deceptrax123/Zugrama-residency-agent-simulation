"""Disposable app + fake Hermes for browser QA. No real model or user data."""
import argparse
import json
from dataclasses import replace
from pathlib import Path
import signal
import sys
import threading

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from residency.config import APP_ROOT
from residency.server import ResidencyServer
from tests.support import JOIN_CODE, gateway, settings


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=7349)
    parser.add_argument('--host-event',action='store_true',help='Seed a three-person host UI fixture; models remain fake')
    parser.add_argument('--identity-test',action='store_true',help='Empty host signup and custom identity fixture; models remain fake')
    parser.add_argument('--full-week',action='store_true',help='Enable fake local memory and seven bedtime phases')
    parser.add_argument('--live-cohort',action='store_true',help='Empty small-cohort host fixture; all providers are fake')
    args = parser.parse_args()
    (APP_ROOT / ".data").mkdir(exist_ok=True)
    with gateway() as backend, settings(hermes_url=backend.url, hermes_key="browser-test-only") as config:
        config = replace(config, public_origin=f"http://127.0.0.1:{args.port}")
        if args.identity_test or args.live_cohort:
            config=replace(config,hermes_model='gpt-5.6-terra')
            backend.models=[{'id':'gpt-5.6-terra','root':'gpt-5.6-terra'}]
            backend.budget_guard='residency-usd-v1'
            backend.usage={'prompt_tokens':1000,'completion_tokens':100,'total_tokens':1100}
        server = ResidencyServer(("127.0.0.1", args.port), config)
        if args.identity_test or args.live_cohort:
            from residency.sandbox import IdentitySandbox
            if args.live_cohort:
                from residency.cohort import LiveCohort
                server.sandbox=LiveCohort(server)
            else:server.sandbox = IdentitySandbox(server)
            from residency import website
            website.fetch_page=lambda url:{'url':url,'text':'Built Solar Atlas, a mapping product.','truncated':False}
            from residency.local_mem0 import AgentMem0
            from tests.test_local_memory import FakeMemory
            fake_memory=FakeMemory();fake_memory.health=lambda:{'status':'ready'}
            server.semantic=AgentMem0(server,fake_memory)
            if args.full_week or args.live_cohort:
                from residency.sleep_cycle import SleepCycle
                server.cycle=SleepCycle(server,fake_memory)
            def identity_reply(payload):
                context=json.loads(payload['messages'][-1]['content'])
                if 'cv' in context:
                    quote='Built Python tools for water monitoring.'
                    return json.dumps({'suggestions':[
                        {'field':'skills','text':'Python programming','quote':'Built Python tools\nfor water monitoring.'},
                        {'field':'professional_background','text':'Combines technical and creative work'},
                        {'field':'subject_expertise','text':'Geospatial systems' if context.get('website') else 'Water monitoring'},
                        {'field':'products_built','text':'Solar Atlas: mapping product' if context.get('website') else 'Water-monitoring prototype: built Python tools'},
                    ] if quote in context['cv'] or context.get('website') else []})
                peer=next(person['id'] for person in context['directory'] if person['id']!=context['member_id'])
                return json.dumps({'wait_seconds':3600,'start_conversations':[{'with':peer,'body':'I reconsider that assumption after your example. Could we explore another approach?'}],
                    'join_conversations':[],'messages':[],'leave_conversations':[]})
            backend.reply_factory=identity_reply
        if args.host_event:
            from demo_three import PERSONAS,DEMO_PASSWORD
            from residency.event import HostEvent
            profiles={}
            for persona in PERSONAS:
                token,_=server.store.register({**persona,'password':DEMO_PASSWORD,'join_code':JOIN_CODE})
                member=server.store.authenticate(token)['member_id']
                server.store.logout(token)
                profiles[member]=persona
                server.store.introduce(member,{'body':persona['introduction']})
            server.capture_conversations(profiles)
            server.event=HostEvent(server,next(iter(profiles)),profiles,config.data_dir/'host-event')
            def reply(payload):
                context=json.loads(payload['messages'][-1]['content'])
                peer=next(person['id'] for person in context['directory'] if person['id']!=context['member_id'])
                return json.dumps({'wait_seconds':3600,'start_conversations':[{'with':peer,'body':'I enjoy exploring useful ideas and music together.'}],
                    'join_conversations':[],'messages':[],'leave_conversations':[]})
            backend.reply_factory=reply
        signal.signal(signal.SIGTERM, lambda *_: threading.Thread(target=server.shutdown, daemon=True).start())
        print(f"BROWSER TEST FIXTURE http://127.0.0.1:{server.server_port} · invitation: {JOIN_CODE}", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            server.server_close()


if __name__ == "__main__":
    main()
