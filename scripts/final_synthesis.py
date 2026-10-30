"""Evidence-preserving hierarchical synthesis of validated final-room accounts."""
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor,as_completed
import sys,json
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'scripts')]
from residency.final_results import load,save,compact,ReportModel,BASE_RULES,GLOBAL_SYSTEM,check_refs,cited_complete,validate_event_synthesis
from residency.hermes import Hermes
from runtime_settings import gateway_settings
MAP=BASE_RULES+'''\nInterpret this group of already source-validated room accounts. Preserve their source message IDs. Return {"summary":"...","themes":[{"label":"...","summary":"...","message_ids":["..."],"room_ids":["..."]}],"transitions":[{"explanation":"...","message_ids":["..."]}],"artifact_origins":[{"explanation":"...","message_ids":["..."]}],"limitations":["..."]}. Maximum 8 themes (summary <=650 characters), 6 transitions and 6 artifact origins (explanation <=500 characters). Every item requires nonempty supplied message IDs. Describe actual designs, disagreements, revisions, play and inconclusive exchanges; do not infer influence from similarity. Summary <=1200 characters. Do not substitute room IDs for message IDs.'''

def synthesize(base,model,run,key_prefix=''):
 cards=[]
 for r in run['analysis']['rooms']:
  card={'room_id':r['room_id'],'title':r['title'],'summary':r['summary'][:900],'topics':r['topics'][:4]}
  card['key_points']=[{'text':p['text'][:220],'message_ids':p['message_ids'][:3]} for p in r['key_points'][:3]]
  card['transitions']=r.get('transitions',[])[:2];card['references']=r.get('references',[])[:2];card['artifacts']=r.get('artifacts',[])[:2];cards.append(card)
 chunks=[];chunk=[]
 for card in cards:
  if chunk and len(compact(chunk+[card]).encode())>68000:chunks.append(chunk);chunk=[]
  chunk.append(card)
 if chunk:chunks.append(chunk)
 progress={'status':'running','packets':len(chunks),'packets_done':0,'rooms':len(cards),'errors':[]};save(base/'synthesis-v2-progress.json',progress);outputs={}
 def job(i,items):
  allowed=set()
  def gather(v):
   if isinstance(v,dict):
    for k,x in v.items():
     if k=='message_ids':allowed.update(x)
     gather(x)
   elif isinstance(v,list):
    for x in v:gather(x)
  gather(items)
  assert allowed,'Never dispatch a synthesis packet with all evidence pruned'
  return cited_complete(model,key_prefix+'event-overview-v2-packet-'+str(i),MAP,{'people':run['people'],'rooms':items,'packet_index':i,'packets':len(chunks)},lambda v:check_refs(v,[m for m in run['messages'] if m['id'] in allowed],run['people'],[r['room_id'] for r in items]),run['messages'])
 with ThreadPoolExecutor(max_workers=3) as pool:
  pending={pool.submit(job,i,c):i for i,c in enumerate(chunks)}
  for f in as_completed(pending):
   try:outputs[pending[f]]=f.result();progress['packets_done']+=1
   except Exception as e:progress['errors'].append(str(e)[:300])
   save(base/'synthesis-v2-progress.json',progress);print(compact(progress),flush=True)
 if progress['errors']:
  progress['status']='failed';save(base/'synthesis-v2-progress.json',progress)
  raise RuntimeError('Review failed synthesis packets before continuation')
 notes=[outputs[i] for i in sorted(outputs)];context={'people':run['people'],'source_linked_room_groups':notes,'coverage':{'rooms':len(cards),'groups':len(notes),'strategy':'Hierarchical synthesis over every validated room account. Each group preserves original message IDs. Full transcripts and individual room accounts remain available.'},'counts':{'messages':len(run['messages']),'rooms':len(cards),'boards':len(run['boards']),'programs':sum(t['name']=='python_run' for t in run['tools']),'resident_groups_3_plus':0,'allowance_transfers':len(run['transfers'])}}
 # Shorten synthesis prose when needed, never remove every citation to fit.
 for length in (350,250,160,100):
  if len(compact(context).encode())<82000:break
  reduced=json.loads(compact(notes))
  for note in reduced:
   note['summary']=note['summary'][:600]
   for key in ('themes','transitions','artifact_origins'):
    for item in note[key]:
     for field in ('summary','explanation'):
      if field in item:item[field]=item[field][:length]
     item['message_ids']=item['message_ids'][:3]
     if 'room_ids' in item:item['room_ids']=item['room_ids'][:3]
  context['source_linked_room_groups']=reduced
 context['coverage']['reduction']='When necessary, prose and citation lists are bounded per item. Each retained item keeps source IDs; original detailed room accounts remain in the report.'
 # Bounded thematic panels avoid a single oversized/long-running response.
 panel_groups=[notes[i:i+3] for i in range(0,len(notes),3)]
 panels={}
 panel_system=GLOBAL_SYSTEM+'\nThis is one thematic panel, not the whole event. Use at most 4 findings, 8 topics, 12 topic-flow edges, 10 ideas, 12 lineage edges, 4 communities and 3 blog sections. Paragraphs <=160 words. Every cited item needs nonempty supplied source IDs. Preserve concrete artifacts and disagreements, but do not invent cross-room influence.'
 def panel_job(i,group):
  return cited_complete(model,key_prefix+'event-presentation-panel-'+str(i),panel_system,{'people':run['people'],'source_linked_room_groups':group,'coverage':'One group of validated room accounts; other panels are separate. Full raw conversations remain available.'},lambda v:validate_event_synthesis(v,run['messages'],run['people'],[r['id'] for r in run['rooms']]),run['messages'])
 with ThreadPoolExecutor(max_workers=3) as pool:
  pending={pool.submit(panel_job,i,g):i for i,g in enumerate(panel_groups)}
  for future in as_completed(pending):
   try:panels[pending[future]]=future.result()
   except Exception as error:progress['errors'].append(str(error)[:300])
   progress['presentation_panels_done']=len(panels);save(base/'synthesis-v2-progress.json',progress)
 if progress['errors']:
  progress['status']='failed';save(base/'synthesis-v2-progress.json',progress)
  raise RuntimeError('Review presentation panel failure before proceeding')
 result={k:[] for k in ('findings','topics','topic_flow','ideas','lineage','communities','blog_sections','limitations')}
 for i in sorted(panels):
  panel=json.loads(compact(panels[i]));prefix='p'+str(i+1)+'-'
  for key,edge_key in (('topics','topic_flow'),('ideas','lineage')):
   for node in panel[key]:node['id']=prefix+node['id']
   for edge in panel[edge_key]:edge['from_id']=prefix+edge['from_id'];edge['to_id']=prefix+edge['to_id']
  for key in result:result[key].extend(panel[key])
 outline={k:[{field:(value[:180] if isinstance(value,str) else value[:2] if field=='message_ids' else value) for field,value in item.items() if field in ('id','label','summary','title','body','message_ids')} for item in result[k]] for k in ('findings','topics','ideas')}
 bridge_system=BASE_RULES+'\nConnect these already source-linked thematic panels into one presentation. Return {"headline":"...","summary":"150-250 words","topic_flow":[{"from_id":"supplied topic ID","to_id":"supplied topic ID","explanation":"...","confidence":"low|medium|high","message_ids":["..."]}],"lineage":[{"from_id":"supplied idea ID","to_id":"supplied idea ID","relation":"branch|refinement|challenge|merge|similarity|reported relay","explanation":"...","confidence":"low|medium|high","message_ids":["..."]}],"blog_sections":[{"title":"...","body":"120-180 words","message_ids":["..."]}]}. Maximum 8 cross-panel topic edges, 8 idea edges, and 2 opening/concluding blog sections. Explain relationships as hypotheses; resemblance does not establish transmission. Cite only supplied nonempty message IDs. Do not invent a link merely to connect the graph.'
 def bridge_valid(v):
  check_refs(v,run['messages'],run['people'],[r['id'] for r in run['rooms']])
  for key,nodes in (('topic_flow',result['topics']),('lineage',result['ideas'])):
   ids={n['id'] for n in nodes}
   if any(e['from_id'] not in ids or e['to_id'] not in ids for e in v[key]):raise ValueError('Cross-panel edge has an unknown endpoint')
  return v
 try:
  bridge=cited_complete(model,key_prefix+'event-presentation-bridges',bridge_system,{'panels':outline,'counts':context['counts'],'coverage':'Every final-event room was reviewed; detailed room accounts and transcripts remain available.'},bridge_valid,run['messages'])
 except Exception as error:
  progress['status']='failed';progress['errors'].append(str(error)[:300]);save(base/'synthesis-v2-progress.json',progress)
  raise
 result['headline']=bridge['headline'];result['summary']=bridge['summary'];result['topic_flow'].extend(bridge['topic_flow']);result['lineage'].extend(bridge['lineage']);result['blog_sections']=bridge['blog_sections']+result['blog_sections'];result['limitations']=list(dict.fromkeys(result['limitations']))
 validate_event_synthesis(result,run['messages'],run['people'],[r['id'] for r in run['rooms']])
 run['analysis']['coverage']={'strategy':'Every populated room has an individual account, followed by source-preserving hierarchical overview synthesis. Long source bodies are excerpted.','messages_reviewed':len(run['messages']),'messages_total':len(run['messages']),'packets':len(chunks),'validated_packets':len(outputs)}
 progress['status']='completed';save(base/'synthesis-v2-progress.json',progress)
 return result

def main():
 base=ROOT/'.data/live-residency/final-results/5ca0be9108194c68af3b0f0d8fda0e64';bundle=load(base/'bundle.json');run=next(r for r in bundle['runs'] if r['id']==bundle['current_event_id']);setup=load(ROOT/'.data/live-residency/setup.json');model=ReportModel(base,Hermes(gateway_settings(ROOT/'.data/live-residency/state',setup['join_code'],model='gpt-6.1-sol',reasoning_effort='high')),budget_usd=25)
 run['analysis']['event']=synthesize(base,model,run)
 save(base/'bundle.json',bundle)
 status=load(base/'progress.json');status['assembly_history']=status.get('errors',[]);status['errors']=[];status['status']='completed';status['synthesis']='Evidence-preserving hierarchical panels';save(base/'progress.json',status)
if __name__=='__main__':main()
