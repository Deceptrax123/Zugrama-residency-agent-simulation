"""Build labelled report reconstructions; never modifies source simulation logs."""
from pathlib import Path
import base64,hashlib,io,json,math,random,struct,wave
ROOT=Path(__file__).resolve().parents[1];base=ROOT/'.data/live-residency/final-results/5ca0be9108194c68af3b0f0d8fda0e64';bundle=json.loads((base/'bundle.json').read_text());bundle['source_sha256']=hashlib.sha256((base/'frozen.sqlite3').read_bytes()).hexdigest();bundle['chess']=json.loads((base/'chess.json').read_text());run=next(r for r in bundle['runs'] if r['id']==bundle['current_event_id']);
# Include only already validated intermediate outputs in a working preview.
room_reports={}
for path in (base/'model').glob('rooms-*/validated.json'):
 key=int(path.parent.name.split('-')[1]);room_reports[key]=json.loads(path.read_text())['rooms']
if room_reports:run['analysis']['rooms']=[r for i in sorted(room_reports) for r in room_reports[i]]
answers=[json.loads(path.read_text()) for path in (base/'assessments').glob('*/ANSWER.json')]
if answers:run['analysis']['agents']=answers
if (base/'model/event-synthesis/validated.json').exists():run['analysis']['event']=json.loads((base/'model/event-synthesis/validated.json').read_text())
# Account for facilitator visits separately from the resident population.
import sqlite3
with sqlite3.connect('file:'+str(base/'frozen.sqlite3')+'?mode=ro',uri=True) as db:names=dict(db.execute('SELECT id,name FROM members'))
for archived in bundle['runs']:
 known={p['id'] for p in archived['people']};extras={v['member_id'] for room in archived['rooms'] for v in room['visits']}-known
 for member in sorted(extras):archived['people'].append({'id':member,'name':names.get(member,'Archived participant'),'nickname':'','facilitator':names.get(member)=='Facilitator NPC'})
observations=json.loads((base/'audit-observations.json').read_text()) if (base/'audit-observations.json').exists() else {}
import statistics
for archived in bundle['runs']:
 archived['observations']=observations.get(archived['id']);counts=[r['message_count'] for r in archived['rooms'] if r['message_count']];resident_ids={p['id'] for p in archived['people'] if not p.get('facilitator')};pairs={tuple(sorted(set(r['participants'])&resident_ids)) for r in archived['rooms'] if r['message_count']}
 archived['room_stats']={'median_messages':statistics.median(counts) if counts else 0,'longest_messages':max(counts,default=0),'resident_pair_sets':len(pairs)}
for assessment in run['analysis']['agents']:
 # Retain the provenance of salvaged Q1 answers separately from the new Q2 packet.
 coverage1=None
 for path in (base/'model').glob('*/response.json'):
  try:
   value=json.loads(path.read_text());answer=json.loads(value['choices'][0]['message']['content']);networking=answer.get('networking',answer)
   if networking==assessment['networking']:
    request=json.loads((path.parent/'request.json').read_text());context=json.loads(request['messages'][-1]['content']);coverage1=context.get('coverage');break
  except Exception:pass
 if coverage1:assessment['coverage']={'networking':coverage1,'judgment':assessment['coverage'],'private_fields_omitted':True}
if (base/'hops.json').exists():bundle['hops']=json.loads((base/'hops.json').read_text())
if (base/'editorial-citation-corrections.json').exists():
 fixes=json.loads((base/'editorial-citation-corrections.json').read_text());bundle['coverage']['editorial_corrections']=str(len(fixes['corrections']))+' citation identifier typos in intermediate overview notes were corrected by an investigator after checking the original message text. Model prose and raw responses were retained; no original conversation, code, questionnaire quote or event state was changed.'
if (base/'report-usage.json').exists():
 entries=json.loads((base/'report-usage.json').read_text());bundle['post_event_usage']={'budget_usd':25,'estimated_usd':sum(e.get('cost_usd',0) for e in entries)/1e6,'held_usd':sum(e.get('hold_usd',0) for e in entries if e['status'] in ('pending','unknown'))/1e6,'entries':[{k:e.get(k) for k in ('key','status','cost_usd','hold_usd','input_tokens','output_tokens')} for e in entries]}
rate=22050;beat=60/112;slot=beat/2;duration=32*slot+.6;samples=[0.0]*int(duration*rate);rand=random.Random(194)
notes=[['.']*8,['.','D4','.','.','.','A4','.','E4'],['.']*8,['.','D4','.','F4','.','A4','G4','E4']];freq={'D4':293.6648,'F4':349.2282,'A4':440,'G4':391.9954,'E4':329.6276}
def add(at,length,fn):
 start=int(at*rate)
 for i in range(min(int(length*rate),len(samples)-start)):
  t=i/rate;samples[start+i]+=fn(t)
for bar in range(4):
 for i in (0,4):add((bar*8+i)*slot,.20,lambda t:.34*math.sin(2*math.pi*(58*t+4*(1-math.exp(-t*50))))*math.exp(-t*24))
 for i in (2,6):add((bar*8+i)*slot,.09,lambda t:.16*rand.uniform(-1,1)*math.exp(-t*45))
 for i in ((1,5,7) if bar%2==0 else (0,3,6)):add((bar*8+i)*slot,.045,lambda t:.10*rand.uniform(-1,1)*math.exp(-t*70))
 for i,n in enumerate(notes[bar]):
  if n!='.':add((bar*8+i)*slot,.19,lambda t,f=freq[n]:.20*(math.sin(2*math.pi*f*t)+.15*math.sin(2*math.pi*f*2*t))*min(1,t/.008)*math.exp(-t*15))
peak=max(abs(s) for s in samples);out=io.BytesIO()
with wave.open(out,'wb') as wav:wav.setnchannels(1);wav.setsampwidth(2);wav.setframerate(rate);wav.writeframes(b''.join(struct.pack('<h',int(s/max(1,peak)*28000)) for s in samples))
bundle['media']={'music':{'board_id':'b2b3a66dbdc54528a121442d700f5228','title':'Four-bar rhythm exchange','bpm':112,'melody':notes,'audio':'data:audio/wav;base64,'+base64.b64encode(out.getvalue()).decode(),'note':'New report synthesis of the exact written eighth-note grid, D4/F4/A4/G4/E4 notes and proposed 112 BPM. Percussion sounds, envelopes and note lengths are editorial approximations. The agents wrote the sketch; no original audition or performance was recorded.'},'choreography_board_id':'71b6296fa1634718847d0d8b357de679'}
if (base/'progress.json').exists():bundle['assessment_status']=json.loads((base/'progress.json').read_text())
path=base/'presentation.json';path.write_text(json.dumps(bundle,ensure_ascii=False,separators=(',',':')));print('Presentation bytes',path.stat().st_size)
# Report only key paths, never private values.
forbidden={'private_memory','own_memories','identity','starting_identities','person_notes','cv_evidence','host_token','password','token','payload'};bad=[]
def scan(x,path=''):
 if isinstance(x,dict):
  for k,v in x.items():
   if k in forbidden:bad.append(path+'.'+k)
   scan(v,path+'.'+k)
 elif isinstance(x,list):
  for i,v in enumerate(x):scan(v,path+'['+str(i)+']')
scan(bundle);print('Forbidden key paths',bad[:30])
