"""Interpret both earlier archives without giving their histories to fresh-event agents."""
from pathlib import Path
import sys,json,collections,threading
from concurrent.futures import ThreadPoolExecutor,as_completed
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'scripts')]
from residency.final_results import load,save,compact,ReportModel,BASE_RULES,GLOBAL_SYSTEM,check_refs,validate_event_synthesis,cited_complete
from residency.hermes import Hermes
from runtime_settings import gateway_settings
MAP=BASE_RULES+'''\nThis is a chronological excerpt packet from an earlier archived run. Return {"summary":"...","topics":[{"label":"...","summary":"...","message_ids":["..."]}],"ideas":[{"label":"...","summary":"...","message_ids":["..."]}],"transitions":[{"explanation":"...","message_ids":["..."]}],"agent_observations":[{"owner_id":"supplied person ID","text":"what this agent actually contributed, questioned or left open in this packet","message_ids":["..."]}],"uncertainties":["..."]}. Max 8 topics, 8 ideas, 8 transitions and one observation per supplied person who has evidence. Text fields max 700 characters, agent text max 450 characters. Every item needs source messages. Do not invent depth for repeated greetings or minimal exchanges. Different conversation IDs remain separate rooms; a continuing pair does not imply the agents retained context across them.'''
AGENTS=BASE_RULES+'''\nWrite researcher reconstructions, not agent self-reports or questionnaires, for EVERY target resident. Use the supplied observations of the archive. Return {"agents":[{"owner_id":"target ID","title":"...","overview":"80-140 words","chapters":[{"title":"...","body":"40-80 words","message_ids":["..."]}],"unresolved":["..."]}]}. At most 3 chapters, at most 3 unresolved points. A resident with no supported contribution should be described with that limitation, not invented participation. Never imply an agent witnessed someone else's private room. No private identity or psychology is supplied. Cite only IDs in the supplied observations.'''

def main():
 base=ROOT/'.data/live-residency/final-results/5ca0be9108194c68af3b0f0d8fda0e64';bundle=load(base/'bundle.json');setup=load(ROOT/'.data/live-residency/setup.json');model=ReportModel(base,Hermes(gateway_settings(ROOT/'.data/live-residency/state',setup['join_code'],model='gpt-6.1-sol',reasoning_effort='high')),budget_usd=25)
 source_messages=[]
 def complete(key,system,context,validate):return cited_complete(model,key,system,context,validate,source_messages)
 for run in bundle['runs']:
  if run['id']==bundle['current_event_id']:continue
  source_messages=run['messages']
  prefix='archive-'+run['id'][:8];chunks=[];chunk=[]
  for m in run['messages']:
   item={**m,'body':m['body'][:1200],'text_clipped':len(m['body'])>1200}
   if chunk and len(compact(chunk+[item]).encode())>76000:chunks.append(chunk);chunk=[]
   chunk.append(item)
  if chunk:chunks.append(chunk)
  stage={'event_id':run['id'],'status':'running','chunks':len(chunks),'chunks_done':0,'errors':[]};save(base/(prefix+'-progress.json'),stage);outputs={};lock=threading.RLock()
  def map_job(i,items):
   value=complete(prefix+'-chunk-'+str(i),MAP,{'people':run['people'],'chunk_index':i,'chunks':len(chunks),'messages':items,'coverage':'Every message is included in exactly one chronological packet; bodies longer than 1200 characters are explicitly excerpted.'},lambda v:check_refs(v,items,run['people'],[r['id'] for r in run['rooms']]))
   with lock:outputs[i]=value;stage['chunks_done']+=1;save(base/(prefix+'-progress.json'),stage)
  with ThreadPoolExecutor(max_workers=3) as pool:
   pending={pool.submit(map_job,i,c):i for i,c in enumerate(chunks)}
   for f in as_completed(pending):
    try:f.result()
    except Exception as e:stage['errors'].append({'chunk':pending[f],'error':str(e)[:250]})
    save(base/(prefix+'-progress.json'),stage);print(compact(stage),flush=True)
  notes=[outputs[i] for i in sorted(outputs)]
  compressed=[]
  for topic_limit,idea_limit,transition_limit,text_limit in ((6,2,1,120),(5,2,1,90),(4,1,1,70),(3,1,0,50)):
   compressed=[]
   for index,n in enumerate(notes):
    compact_note={'packet_index':index,'summary':n['summary'][:text_limit*2]}
    for key,maximum in [('topics',topic_limit),('ideas',idea_limit),('transitions',transition_limit)]:
     compact_note[key]=[{k:(v[:text_limit] if isinstance(v,str) else v[:2] if k=='message_ids' else v) for k,v in item.items()} for item in n.get(key,[])[:maximum]]
    compressed.append(compact_note)
   context={'people':run['people'],'archival_packets':compressed,'coverage':{'messages':len(run['messages']),'chunks':len(chunks),'validated_chunks':len(notes),'reduction':'Every packet represented by its strongest bounded themes; complete packet notes remain in the archive.'},'counts':{'messages':len(run['messages']),'populated_rooms':sum(bool(r['message_count']) for r in run['rooms']),'boards':len(run['boards']),'programs':sum(t['name']=='python_run' for t in run['tools'])}}
   if len(compact(context).encode())<80000:break
  run['analysis']['packet_notes']=notes
  try:run['analysis']['event']=complete(prefix+'-synthesis',GLOBAL_SYSTEM+'\nThe inputs are validated chronological packet notes from one earlier run, not the final event. Cover the entire supplied run. Repeated introductions, short-lived rooms and thin evidence are valid findings.',context,lambda v:validate_event_synthesis(v,run['messages'],run['people'],[r['id'] for r in run['rooms']]))
  except Exception as e:stage['errors'].append({'task':'synthesis','error':str(e)[:300]})
  archived_agents={}
  def people_job(targets):
   ids={p['id'] for p in targets};observations=[o for n in notes for o in n.get('agent_observations',[]) if o.get('owner_id') in ids];context={'targets':targets,'observations':observations,'activity':[a for a in run['agent_stats'] if a['id'] in ids]}
   for limit in (450,300,180,100):
    if len(compact(context).encode())<82000:break
    context['observations']=[{**o,'text':o.get('text','')[:limit]} for o in observations]
   def validate(v):
    if {p['owner_id'] for p in v['agents']}!=ids:raise ValueError('An archived resident account is missing')
    return check_refs(v,run['messages'],run['people'],[r['id'] for r in run['rooms']])
   value=complete(prefix+'-people-'+targets[0]['id'],AGENTS,context,validate)
   with lock:
    for a in value['agents']:archived_agents[a['owner_id']]=a
  people=[p for p in run['people'] if not p.get('facilitator')]
  with ThreadPoolExecutor(max_workers=3) as pool:
   pending=[pool.submit(people_job,people[i:i+3]) for i in range(0,len(people),3)]
   for future in as_completed(pending):
    try:future.result()
    except Exception as e:stage['errors'].append({'task':'resident stories','error':str(e)[:300]})
  run['analysis']['archival_agents']=list(archived_agents.values());run['analysis']['coverage']={'strategy':'Chronological map/reduce over every recorded message, with bodies capped at 1200 characters. Individual resident accounts are researcher reconstructions, not questionnaires.','messages_reviewed':sum(len(chunks[i]) for i in outputs),'messages_total':len(run['messages']),'packets':len(chunks),'validated_packets':len(outputs)};stage['status']='completed' if not stage['errors'] else 'completed_with_gaps';save(base/(prefix+'-progress.json'),stage);save(base/'bundle.json',bundle)
 # Cross-run blog, grounded in the separate event reports and exact counts.
 source_messages=[m for r in bundle['runs'] for m in r['messages']]
 reports=[{'event_id':r['id'],'counts':{'messages':len(r['messages']),'rooms':sum(bool(x['message_count']) for x in r['rooms']),'boards':len(r['boards']),'programs':sum(t['name']=='python_run' for t in r['tools'])},'analysis':json.loads(compact(r['analysis'].get('event')))} for r in bundle['runs']]
 context={'runs':reports,'limitations':bundle['coverage']}
 if len(compact(context).encode())>84000:
  for r in reports:
   if r['analysis']:r['analysis'].pop('blog_sections',None)
 system=BASE_RULES+'''\nWrite a presentation-to-blog narrative across all three separate archived runs. Return {"headline":"...","summary":"...","sections":[{"title":"...","body":"150-300 words","message_ids":["..."]}],"nodes":[{"id":"n1","label":"run + theme","summary":"...","event_id":"supplied run ID","message_ids":["..."]}],"edges":[{"from_id":"n1","to_id":"n2","relation":"similarity|contrast|recurrence","explanation":"...","confidence":"low|medium|high","message_ids":["..."]}],"limitations":["..."]}. Max 10 sections, 18 comparative theme nodes and 26 edges. The nodes compare themes across separate runs; they are not proof of continuity or transmission across a fresh restart. Distinguish changed conditions from outcomes; do not attribute differences causally to memory. Topics/ideas concern live conversations only. The two questionnaires occurred after the final host stop and cannot be evidence of what agents discussed during networking. Include creative play, what led to artifacts, limits/failures, and the absence of three-resident groups or actual allowance transfers. Never invent success or causality. Each section needs supplied message evidence.'''
 def validate_study(v):
  check_refs(v,[m for r in bundle['runs'] for m in r['messages']],[p for r in bundle['runs'] for p in r['people']],[room['id'] for r in bundle['runs'] for room in r['rooms']])
  ids={n['id'] for n in v['nodes']};runs={r['id'] for r in bundle['runs']}
  if len(ids)!=len(v['nodes']) or any(n['event_id'] not in runs for n in v['nodes']) or any(e['from_id'] not in ids or e['to_id'] not in ids for e in v['edges']):raise ValueError('Invalid cross-run graph provenance')
  if not v['sections']:raise ValueError('Missing cross-run narrative')
  return v
 try:bundle['study']=complete('cross-run-blog',system,context,validate_study)
 except Exception as e:bundle['study_error']=str(e)[:300]
 bundle['coverage']['semantic_focus']='All recorded messages across three runs were reviewed through bounded, source-linked hierarchical model analysis. Final-event rooms have individual accounts; earlier runs use chronological packets and researcher resident accounts. Only the final event has post-stop agent questionnaires. Short internal citation aliases are mapped back to original message IDs without changing source text.'
 save(base/'bundle.json',bundle)
if __name__=='__main__':main()
