"""Deliver completed assessment links privately without restarting any agent."""
from pathlib import Path
import json,sqlite3,sys,time,os
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'scripts')]
from residency.end_questionnaire import render_answer
from residency.final_results import load,save

def main():
 os.umask(0o077)
 base=ROOT/'.data/live-residency/final-results/5ca0be9108194c68af3b0f0d8fda0e64';state=load(base/'state.json');live=load(ROOT/'.data/live-residency/state/host-event/state.json');assert state['event_id']==live['event_id'] and live['status'] not in ('running','stopping') and not live.get('thinking');bundle=load(base/'presentation.json');run=next(r for r in bundle['runs'] if r['id']==state['event_id']);answers={a['owner_id']:a for a in run['analysis']['agents']};assert set(answers)==set(state['starting_identities']),'Every resident needs a complete validated pair first'
 origin=load(ROOT/'.data/live-residency/site-bridge.json')['origin'];directory=base/'assessments';people={p['id']:p['name'] for p in run['people']}
 frozen=sqlite3.connect('file:'+str(base/'frozen.sqlite3')+'?mode=ro',uri=True);frozen.row_factory=sqlite3.Row
 from residency.final_results import questionnaire_context
 for owner,a in answers.items():
  packet=questionnaire_context(frozen,state,owner,base);packet['messages']=run['messages'];text=render_answer(a['networking'],packet);(directory/owner/'QUESTIONNAIRE_1.md').write_text(text)
  lines=['# Judgment, influence & shared responsibility','',people[owner],'','Agent self-report after the host stop. Public starting fields and witnessed excerpts only.','']
  for q in bundle['questionnaires']['questionnaires'][1]['questions']:
   row=a['judgment'][q['id']];lines+=['## '+q['prompt'],'',row['answer'],'']
   for e in row['evidence']:
    m=next(m for m in run['messages'] if m['id']==e['message_id']);lines+=['> '+e['quote'].replace('\n','\n> '),'',f"Speaker: {people.get(m['sender_id'],m['sender_id'])} · Message {m['id']} · Conversation {m['conversation_id']}",'']
   if row['paper_sections']:lines+=['Paper guide: '+', '.join(row['paper_sections']),'']
  (directory/owner/'QUESTIONNAIRE_2.md').write_text('\n'.join(lines))
 frozen.close()
 db=sqlite3.connect(ROOT/'.data/live-residency/state/residency.sqlite3',timeout=30);db.execute('BEGIN IMMEDIATE')
 for owner,a in answers.items():
  link=origin+'/results?run='+state['event_id']+'&view=questionnaires&agent='+owner
  for n,title in [(1,'Conversations, learning & collaboration'),(2,'Judgment, influence & shared responsibility')]:
   identifier=f'final-questionnaire-{state["event_id"]}-{owner}-{n}';body=f'Completed end-of-event questionnaire {n}: {title}';response=f'Your agent completed questionnaire {n} after the host stopped the event.\n\nRead the complete answer with conversation evidence:\n{link}\n\nUse the shared residency code. The response is an agent self-report, not a measured human outcome. The full report distinguishes witnessed evidence from interpretation. Opening it does not restart the event.'
   db.execute("INSERT OR IGNORE INTO agent_requests VALUES(?,?,NULL,?,'addressed',?,?,?)",(identifier,owner,body,response,time.time(),state['event_id']))
 db.commit();count=db.execute("SELECT count(*) FROM agent_requests WHERE event_id=? AND id LIKE 'final-questionnaire-%'",(state['event_id'],)).fetchone()[0];db.close();save(base/'delivery.json',{'event_id':state['event_id'],'addressed_response_records':count,'owners':len(answers),'networking_resumed':False,'at':time.time()});print('Delivered private answer links:',count)
if __name__=='__main__':main()
