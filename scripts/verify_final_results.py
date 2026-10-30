"""Offline integrity checks for the frozen report. Never dispatches model calls."""
from pathlib import Path
import argparse,hashlib,json,sqlite3,sys
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'scripts')]
from final_hops import validate_hops


def verify(base,latest_only=False):
    data=json.loads((base/'presentation.json').read_text())
    progress=base/'transport-repair-progress.json'
    if progress.exists():assert json.loads(progress.read_text())['status']=='completed','Transport review is not complete'
    assert data['source_sha256']==hashlib.sha256((base/'frozen.sqlite3').read_bytes()).hexdigest(),'Frozen database hash mismatch'
    forbidden={'private_memory','own_memories','identity','starting_identities','person_notes','cv_evidence','host_token','password','token','payload'}
    def private_scan(v):
        if isinstance(v,dict):
            assert not forbidden.intersection(v),'Private field in shared report'
            for x in v.values():private_scan(x)
        elif isinstance(v,list):
            for x in v:private_scan(x)
    private_scan(data)
    all_messages={m['id']:m for r in data['runs'] for m in r['messages']}
    all_people={p['id'] for r in data['runs'] for p in r['people']}
    def refs(v,messages,people,rooms):
        if isinstance(v,dict):
            for k,x in v.items():
                if k in ('message_id','source_message_id','relay_message_id','receipt_message_id') and x:assert x in messages,(k,x)
                if k=='message_ids':assert set(x)<=messages,(k,set(x)-messages)
                if k in ('member_ids',):assert set(x)<=people,(k,x)
                if k in ('room_id','conversation_id') and x:assert x in rooms,(k,x)
                if k=='room_ids':assert set(x)<=rooms,(k,x)
                refs(x,messages,people,rooms)
        elif isinstance(v,list):
            for x in v:refs(x,messages,people,rooms)
    def graph(nodes,edges):
        ids={n['id'] for n in nodes};assert len(ids)==len(nodes),'Duplicate graph node'
        assert all(e['from_id'] in ids and e['to_id'] in ids for e in edges),'Unknown graph endpoint'
    counts=[]
    for run in data['runs']:
        messages={m['id']:m for m in run['messages']};people={p['id'] for p in run['people']};rooms={r['id'] for r in run['rooms']}
        assert len(messages)==len(run['messages'])
        for m in messages.values():
            assert m['sender_id'] in people and set(m['recipients'])<=people
            assert m['conversation_id'] in rooms
        assert sum(r['message_count'] for r in run['rooms'])==len(messages)
        for room in run['rooms']:assert room['message_count']==sum(m['conversation_id']==room['id'] for m in messages.values())
        refs(run['analysis'],set(messages),people,rooms)
        refs(run['boards'],set(messages),people,rooms);refs(run['tasks'],set(messages),people,rooms)
        for tool in run['tools']:
            assert tool['owner_id'] in people
            assert set(tool['context_message_ids']+tool['produced_message_ids'])<=set(messages),'Dangling tool provenance'
        assert all(board['message_id'] in messages and board['owner_id'] in people for board in run['boards'])
        event=run['analysis'].get('event')
        if not latest_only or run['id']==data['current_event_id']:
            assert event,'Missing run synthesis'
            for key in ('headline','summary','findings','topics','topic_flow','ideas','lineage','communities','blog_sections','limitations'):assert key in event,('Missing synthesis field',key)
            graph(event['topics'],event['topic_flow']);graph(event['ideas'],event['lineage'])
        residents={p['id'] for p in run['people'] if not p.get('facilitator')}
        if run['id']==data['current_event_id']:
            assert {x['room_id'] for x in run['analysis']['rooms']}=={r['id'] for r in run['rooms'] if r['message_count']},'Missing room account'
            assert len(run['analysis']['agents'])==len(residents)==21
            assert {a['owner_id'] for a in run['analysis']['agents']}==residents
            question_ids={q['id'] for q in data['questionnaires']['questionnaires'][1]['questions']}
            for a in run['analysis']['agents']:
                owner=a['owner_id'];witnessed={m['id'] for m in messages.values() if m['sender_id']==owner or owner in m['recipients']}
                contacts={p for m in messages.values() if m['id'] in witnessed for p in [m['sender_id'],*m['recipients']] if p!=owner and p in residents}
                assert set(a['networking']['ranking'])==contacts and len(a['networking']['ranking'])==len(contacts),'Ranking has missing/extra contact'
                assert set(a['judgment'])==question_ids,'Missing questionnaire item'
                answers=[v for k,v in a['networking'].items() if k!='ranking']+list(a['judgment'].values())
                for answer in answers:
                    assert answer['answer'].strip()
                    for evidence in answer['evidence']:
                        assert evidence['message_id'] in witnessed,'Questionnaire uses unseen conversation'
                        assert evidence['quote'] in messages[evidence['message_id']]['body'],'Questionnaire quote is not exact'
                refs(a['story'],witnessed,people,rooms)
            assert data.get('hops') is not None,'Missing relay assessment'
            validate_hops(data['hops'],run,set(messages))
        elif not latest_only:
            assert {a['owner_id'] for a in run['analysis']['archival_agents']}==residents,'Missing archival resident account'
            coverage=run['analysis']['coverage'];assert coverage['messages_reviewed']==coverage['messages_total']==len(messages)
            assert coverage['validated_packets']==coverage['packets']
        counts.append({'event':run['id'],'messages':len(messages),'rooms':sum(bool(r['message_count']) for r in run['rooms'])})
    if latest_only:assert 'publication_scope' in data['coverage'] and data['assessment_status']['status']=='latest_event_ready','An incomplete archive must be explicitly labelled'
    else:
        assert data.get('study'),'Missing cross-run synthesis'
        refs(data['study'],set(all_messages),all_people,{r['id'] for run in data['runs'] for r in run['rooms']})
        graph(data['study']['nodes'],data['study']['edges'])
        assert all(n['event_id'] in {r['id'] for r in data['runs']} for n in data['study']['nodes'])
    assert len(data.get('chess',[]))==2 and all(not game['error'] for game in data['chess'])
    for game in data['chess']:assert all(not p.get('message_id') or p['message_id'] in all_messages for p in game['positions'])
    ledger=json.loads((base/'report-usage.json').read_text());assert not any(e['status']=='pending' for e in ledger)
    committed=sum(e.get('cost_usd',0)+(e.get('hold_usd',0) if e['status']=='unknown' else 0) for e in ledger)/1e6
    assert committed<=data['post_event_usage']['budget_usd']
    report={'passed':True,'scope':'latest_event_and_all_raw_archives' if latest_only else 'all_runs','presentation_sha256':hashlib.sha256((base/'presentation.json').read_bytes()).hexdigest(),'source_sha256':data['source_sha256'],'runs':counts,'questionnaire_pairs':21,'messages':len(all_messages),'two_hop_cases':len(data['hops']['chains']),'report_committed_usd':round(committed,6)}
    (base/'integrity.json').write_text(json.dumps(report,indent=2));return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--base',type=Path,default=ROOT/'.data/live-residency/final-results/5ca0be9108194c68af3b0f0d8fda0e64');parser.add_argument('--latest',action='store_true');args=parser.parse_args();print(json.dumps(verify(args.base,args.latest),indent=2))
