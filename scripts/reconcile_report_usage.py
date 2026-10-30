"""Recover terminal native usage for timed-out report calls without replaying them."""
from pathlib import Path
import hashlib,json,sqlite3,sys,time
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'scripts')]
from residency.final_results import load,save
from residency.report_transport import native_text

def recovery(entry,request,db):
    sid='final-report-'+entry['id'];row=db.execute('SELECT model,input_tokens,output_tokens,api_call_count,tool_call_count FROM sessions WHERE id=?',(sid,)).fetchone()
    if not row or row['model']!='gpt-6.1-sol' or row['api_call_count']!=1 or row['tool_call_count']!=0:return None
    if any(type(row[k]) is not int or row[k]<=0 for k in ('input_tokens','output_tokens')):return None
    messages=db.execute('SELECT role,content,finish_reason FROM messages WHERE session_id=? ORDER BY id',(sid,)).fetchall();users=[m for m in messages if m['role']=='user'];answers=[m for m in messages if m['role']=='assistant']
    if len(users)!=1 or users[0]['content']!=native_text(request) or len(answers)!=1 or answers[0]['finish_reason']!='stop':return None
    try:answer=json.loads(answers[0]['content'])
    except (ValueError,TypeError):return None
    if not isinstance(answer,dict):return None
    return {'session_id':sid,'model':row['model'],'input_tokens':row['input_tokens'],'output_tokens':row['output_tokens'],'api_call_count':1,'finish_reason':'stop','native_source_matches_saved_request':True,'answer_sha256':hashlib.sha256(answers[0]['content'].encode()).hexdigest(),'cost_usd':row['input_tokens']*2+row['output_tokens']*10}

def main():
    base=ROOT/'.data/live-residency/final-results/5ca0be9108194c68af3b0f0d8fda0e64';entries=load(base/'report-usage.json');assert not any(e['status']=='pending' for e in entries),'Drain retrospective requests before ledger reconciliation'
    state=load(ROOT/'.data/live-residency/state/host-event/state.json');assert state['event_id']==load(base/'state.json')['event_id'] and state['status'] not in ('running','stopping') and not state.get('thinking')
    db=sqlite3.connect('file:'+str(ROOT/'.hermes/state.db')+'?mode=ro',uri=True);db.row_factory=sqlite3.Row;receipts=[]
    for entry in entries:
        if entry['status']!='unknown':continue
        request=load(base/'model'/entry['key']/'request.json');result=recovery(entry,request,db)
        if result:
            receipts.append({'entry_id':entry['id'],'key':entry['key'],**result});entry.update(status='recorded_usage_recovered',hold_usd=0,cost_usd=result['cost_usd'],input_tokens=result['input_tokens'],output_tokens=result['output_tokens'],usage_source='native session database; one terminal API call; source text hash matched')
    db.close()
    if receipts:
        backup=base/'report-usage.before-native-reconciliation.json'
        if not backup.exists():save(backup,load(base/'report-usage.json'))
        save(base/'native-usage-reconciliation.json',{'at':time.time(),'receipts':receipts,'networking_resumed':False,'calls_replayed':0});save(base/'report-usage.json',entries)
    print(json.dumps({'usage_receipts_recovered':len(receipts),'calls_replayed':0,'unknown_remaining':sum(e['status']=='unknown' for e in entries)}))

if __name__=='__main__':main()
