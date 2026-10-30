"""Evidence-preserving hierarchical synthesis of validated final-room accounts."""
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor,as_completed
import sys,json
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'scripts')]
from residency.final_results import load,save,compact,ReportModel,BASE_RULES,GLOBAL_SYSTEM,check_refs
from residency.hermes import Hermes
from runtime_settings import gateway_settings
MAP=BASE_RULES+'''\nInterpret this group of already source-validated room accounts. Preserve their source message IDs. Return {"summary":"...","themes":[{"label":"...","summary":"...","message_ids":["..."],"room_ids":["..."]}],"transitions":[{"explanation":"...","message_ids":["..."]}],"artifact_origins":[{"explanation":"...","message_ids":["..."]}],"limitations":["..."]}. Maximum 8 themes (summary <=650 characters), 6 transitions and 6 artifact origins (explanation <=500 characters). Every item requires nonempty supplied message IDs. Describe actual designs, disagreements, revisions, play and inconclusive exchanges; do not infer influence from similarity. Summary <=1200 characters. Do not substitute room IDs for message IDs.'''

def synthesize(base,model,run):
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
  return model.complete('event-overview-v2-packet-'+str(i),MAP,{'people':run['people'],'rooms':items,'packet_index':i,'packets':len(chunks)},lambda v:check_refs(v,[m for m in run['messages'] if m['id'] in allowed],run['people'],[r['room_id'] for r in items]))
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
 def validate(v):
  check_refs(v,run['messages'],run['people'],[r['id'] for r in run['rooms']])
  for nodes,edges in ((v['topics'],v['topic_flow']),(v['ideas'],v['lineage'])):
   ids={n['id'] for n in nodes}
   if any(e['from_id'] not in ids or e['to_id'] not in ids for e in edges):raise ValueError('Unknown graph endpoint')
  return v
 try:
  result=model.complete('event-overview-v2-global',GLOBAL_SYSTEM+'\nThe inputs are source-linked thematic summaries of groups of room accounts. Every room was included. Cite only supplied message IDs; never return an item with an empty message_ids list. The summary and limitations can state scope limits without pretending they are transcript quotations.',context,validate)
 except Exception as error:
  progress['status']='failed';progress['errors'].append(str(error)[:300]);save(base/'synthesis-v2-progress.json',progress)
  raise

 run['analysis']['coverage']={'strategy':'Every populated room has an individual account, followed by source-preserving hierarchical overview synthesis. Long source bodies are excerpted.','messages_reviewed':len(run['messages']),'messages_total':len(run['messages']),'packets':len(chunks),'validated_packets':len(outputs)}
 progress['status']='completed';save(base/'synthesis-v2-progress.json',progress)
 return result

def main():
 base=ROOT/'.data/live-residency/final-results/5ca0be9108194c68af3b0f0d8fda0e64';bundle=load(base/'bundle.json');run=next(r for r in bundle['runs'] if r['id']==bundle['current_event_id']);setup=load(ROOT/'.data/live-residency/setup.json');model=ReportModel(base,Hermes(gateway_settings(ROOT/'.data/live-residency/state',setup['join_code'],model='gpt-6.1-sol',reasoning_effort='high')),budget_usd=25)
 run['analysis']['event']=synthesize(base,model,run)
 save(base/'bundle.json',bundle)
 status=load(base/'progress.json');status['assembly_history']=status.get('errors',[]);status['errors']=[];status['status']='completed';status['synthesis']='Evidence-preserving hierarchical v2';save(base/'progress.json',status)
if __name__=='__main__':main()
