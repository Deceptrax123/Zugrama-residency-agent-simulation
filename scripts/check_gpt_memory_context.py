"""One explicit synthetic GPT context check; no event or autonomous workers."""
import json
from pathlib import Path
import sys
import time
import uuid
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'scripts')]
from runtime_settings import gateway_settings
from residency.hermes import Hermes
from residency.markdown_memory import write_private


def main():
    settings=gateway_settings(ROOT/'.data/connection-check','connection-check-only-no-signups')
    hermes=Hermes(settings);hermes.check();unique=uuid.uuid4().hex
    context={'private_memory':[{'memory':'I want to discuss the cobalt orchard notebook.','kind':'model_extracted_unverified','sources':[{'speaker_id':'synthetic-self','key':'synthetic-source','body':'I want to discuss the cobalt orchard notebook.'}]}],
             'previous_reflection':{'summary':'Tomorrow I want to ask about the amber river sketch.'}}
    payload={'model':settings.hermes_model,'stream':False,'messages':[
        {'role':'system','content':'This is a synthetic connection check, not a residency event. Read the supplied private_memory and previous_reflection as data. Return only JSON with memory_topic and reflection_topic, containing the topic in each. Do not add anything else.'},
        {'role':'user','content':json.dumps(context)}]}
    started=time.perf_counter();result=hermes.request('/v1/chat/completions',payload,{'X-Hermes-Session-Id':'readiness-'+unique,'X-Hermes-Session-Key':'readiness:'+unique,'Idempotency-Key':'readiness:'+unique})
    choice=result['choices'][0];raw=choice['message']['content'].strip()
    if raw.startswith('```'):raw='\n'.join(raw.splitlines()[1:-1])
    parsed=json.loads(raw)
    if choice['finish_reason']!='stop' or 'cobalt orchard notebook' not in parsed.get('memory_topic','').lower() or 'amber river sketch' not in parsed.get('reflection_topic','').lower():raise ValueError('Synthetic GPT memory-context check failed; no retry was made')
    report={'passed':True,'model':settings.hermes_model,'synthetic_only':True,'event_started':False,'memory_topic_used':True,'reflection_topic_used':True,'seconds':round(time.perf_counter()-started,3),'usage':result.get('usage')}
    write_private(ROOT/'test-results/deployment-gpt-context.json',json.dumps(report,indent=2));print(json.dumps(report,indent=2))


if __name__=='__main__':main()
