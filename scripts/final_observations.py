"""Aggregate audit metadata only; private prompts and memory text never exported."""
from pathlib import Path
import collections,json,hashlib
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from residency.report_transport import field_exposure,native_text
ROOT=Path(__file__).resolve().parents[1];base=ROOT/'.data/live-residency/final-results/5ca0be9108194c68af3b0f0d8fda0e64';bundle=json.loads((base/'bundle.json').read_text());result={}
for run in bundle['runs']:
 counts=collections.Counter();models=collections.Counter();efforts=collections.Counter();firsts={};retrieval=collections.Counter();variants={};intro=[];environment=''
 for path in sorted((ROOT/'.data/live-residency/audit'/run['id']).glob('*/request.json')):
  try:
   d=json.loads(path.read_text());payload=d['payload'];context=json.loads(payload['messages'][-1]['content']);counts['audited_requests']+=1;models[payload['model']]+=1;efforts[str(payload.get('model_options',{}).get('reasoning',{}).get('effort',payload.get('model_options',{}).get('reasoning_effort','unspecified')))]+=1
   native=native_text(payload);source_text=payload['messages'][-1]['content']
   if len(source_text)>65536:counts['native_input_clipped']+=1
   if context.get('private_memory'):
    counts['private_memory_native_'+field_exposure(source_text,'private_memory',native)]+=1
   if not intro and context.get('introduction_board'):intro=[{k:p.get(k) for k in ('member_id','body','created_at')} for p in context['introduction_board']]
   if not environment:environment=context.get('room_prompt','')
   text=payload['messages'][0]['content'];digest=hashlib.sha256(text.encode()).hexdigest();call=int(path.parent.name)
   variant=variants.setdefault(digest,{'sha256':digest,'first_call':call,'last_call':call,'count':0,'text':text});variant['last_call']=call;variant['count']+=1
   fields={'human_requests_supplied':bool(context.get('human_requests')),'facilitator_supplied':bool(context.get('facilitator')),'private_memory_supplied':bool(context.get('private_memory')),'thread_context_supplied':bool(context.get('conversation_threads')),'shared_task_index_supplied':bool(context.get('workspace_index')),'person_note_index_supplied':bool(context.get('person_notes_index')),'reflection_supplied':bool(context.get('previous_reflection'))}
   access=json.dumps(context.get('tool_access',{}));fields.update(delegate_available='"delegate"' in access,budget_transfer_available='"budget_transfer"' in access,music_notice_supplied=any(n.get('id')=='music-choreography-v1' for n in context.get('new_additions',[])))
   for key,yes in fields.items():
    if yes:counts[key]+=1;firsts.setdefault(key,{'call':int(path.parent.name),'at':d.get('at')})
   status=context.get('memory_retrieval',{}).get('status') if isinstance(context.get('memory_retrieval'),dict) else None
   if status:retrieval[status]+=1
  except (ValueError,KeyError,TypeError):counts['unreadable_requests']+=1
 result[run['id']]={'public_introductions':intro,'environment_prompt':environment,'system_variants':list(variants.values()),'counts':dict(counts),'models':dict(models),'reasoning_efforts':dict(efforts),'first_observed':firsts,'retrieval_status_counts':dict(retrieval),'interpretation':'Supplied counts describe saved application requests. The native Hermes parser capped each single text part at 65,536 characters; native_input_clipped and private_memory_native_full/partial/absent distinguish actual input exposure from saved payloads. A post-event structured transport fix preserves JSON values for future requests; it does not change the historical run. These counts do not establish attention, effective use or causation. Private memory contents and per-resident preferences are excluded.'}
(base/'audit-observations.json').write_text(json.dumps(result,indent=2));print(json.dumps({i:{'requests':v['counts'].get('audited_requests'),'models':v['models'],'memory_nonempty':v['counts'].get('private_memory_supplied',0),'person_index_nonempty':v['counts'].get('person_note_index_supplied',0)} for i,v in result.items()},indent=2))
