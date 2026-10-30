"""Read-only, event-scoped checkpoint export. Never starts/stops agents or settles usage."""
import collections, datetime, hashlib, json, os, pathlib, sqlite3, sys, time

ROOT = pathlib.Path(__file__).resolve().parents[1]

def classify(ended, calls, last, error, remaining):
    if error: return 'worker_error'
    if ended and not calls: return 'ended_before_run'
    if ended and last and last['purpose'] == 'wrap_up': return 'budget_wrap_up'
    if ended and last and last.get('decision', {}).get('budget_choice') in ('end', 'wrap_up'): return 'explicit_end'
    if ended: return 'ended_unexplained'
    if remaining < 1.9: return 'budget_paused'
    return 'remaining_worker'

def read_decision(audit, call):
    path = audit / f'{call:04d}' / 'response.json'
    if not path.exists(): return {}, None
    try:
        response = json.loads(path.read_text())
        response = response.get('response', response)
        content = response['choices'][0]['message']['content'].strip()
        if content.startswith('```'): content = content.split('\n', 1)[1].rsplit('```', 1)[0]
        action = json.loads(content)
        return {k: action[k] for k in ('budget_choice', 'wait_seconds', 'messages') if k in action}, response.get('usage')
    except (ValueError, KeyError, IndexError, TypeError): return {}, None

def export(destination):
    os.umask(0o077)
    state_path = ROOT / '.data/live-residency/state/host-event/state.json'
    state = json.loads(state_path.read_text()); event = state['event_id']; cutoff = time.time()
    db = sqlite3.connect('file:' + str(ROOT / '.data/live-residency/state/residency.sqlite3') + '?mode=ro', uri=True)
    db.row_factory = sqlite3.Row
    db.execute('BEGIN')
    rooms = set(state['conversation_ids']); identities = state['starting_identities']
    members = {r['id']:r['name'] for r in db.execute('SELECT id,name FROM members')}
    names = {owner:members.get(owner, identity['name']) for owner,identity in identities.items()}
    messages = [dict(r) for r in db.execute('SELECT * FROM conversation_messages WHERE created_at<=? ORDER BY created_at,seq', (cutoff,)) if r['conversation_id'] in rooms]
    visits = collections.defaultdict(list)
    for r in db.execute('SELECT * FROM conversation_visits'):
        if r['conversation_id'] in rooms: visits[r['conversation_id']].append(dict(r))
    for m in messages:
        m['recipients'] = sorted({v['member_id'] for v in visits[m['conversation_id']] if v['member_id'] != m['sender_id'] and m['seq'] > v['joined_after_seq'] and (v['left_after_seq'] is None or m['seq'] <= v['left_after_seq'])})
    message_by_id = {m['id']:m for m in messages}
    usage = [dict(r) for r in db.execute('SELECT * FROM agent_usage WHERE event_id=? AND created_at<=? ORDER BY call_number', (event,cutoff))]
    allusage = [dict(r) for r in db.execute('SELECT owner_id,status,cost_usd,hold_usd FROM agent_usage WHERE created_at<=?', (cutoff,))]
    audit = ROOT / '.data/live-residency/audit' / event
    agents = []
    for owner, name in names.items():
        wallet = dict(db.execute('SELECT * FROM agent_wallets WHERE owner_id=?',(owner,)).fetchone())
        own = [r for r in usage if r['owner_id']==owner]
        cumulative = [r for r in allusage if r['owner_id']==owner]
        spent = sum(r['cost_usd'] for r in cumulative)/1e6
        held = sum(r['hold_usd'] for r in cumulative if r['status'] in ('pending','unknown'))/1e6
        remaining = wallet['limit_usd']/1e6-spent-held
        last = None
        if own:
            r = own[-1]; decision, provider_usage = read_decision(audit,r['call_number'])
            last = {k:r[k] for k in ('call_number','purpose','status','created_at')}
            last.update(decision=decision,provider_usage=provider_usage,audit_response_saved=(audit/f"{r['call_number']:04d}"/'response.json').exists(),produced_ids=[l['message_id'] for l in json.loads(r['links']) if l.get('kind')=='produced' and l.get('message_id') in message_by_id])
        outgoing = [m for m in messages if m['sender_id']==owner]
        agents.append(dict(id=owner,name=name,classification=classify(wallet['ended'],own,last,state.get('agent_errors',{}).get(owner),remaining),error=state.get('agent_errors',{}).get(owner),calls=len(own),messages=len(outgoing),last=last,last_message_ids=[m['id'] for m in outgoing[-3:]],budget={'limit_usd':wallet['limit_usd']/1e6,'reserve_usd':wallet['reserve_usd']/1e6,'spent_usd':spent,'held_usd':held,'remaining_usd':remaining,'ended':bool(wallet['ended'])}))
    tools = [{k:r[k] for k in ('id','owner_id','call_number','name','result','status','created_at','finished_at')} for r in db.execute('SELECT * FROM agent_tool_runs WHERE event_id=? AND created_at<=? ORDER BY created_at',(event,cutoff))]
    boards = [dict(r) for r in db.execute('SELECT * FROM agent_boards WHERE event_id=? AND created_at<=? ORDER BY created_at',(event,cutoff))]
    db.rollback(); db.close()
    if json.loads(state_path.read_text())['event_id'] != event: raise RuntimeError('Event changed; export discarded')
    counts = dict(collections.Counter(a['classification'] for a in agents))
    data = dict(schema_version=1,slug='continuation-2026-10-29',title='Where the conversations landed',captured_at=cutoff,event={k:state[k] for k in ('event_id','status','started_at','calls','completed_calls','message_count','protocol')},counts=counts,agents=agents,messages=messages,tools=tools,boards=boards,usage={'requests':len(usage),'recorded_requests':sum(r['status']=='recorded' for r in usage),'unknown_requests':sum(r['status']=='unknown' for r in usage),'rejected_requests':sum(r['status']=='rejected' for r in usage),'tokens':sum(r['total_tokens'] or 0 for r in usage),'estimated_usd':sum(r['cost_usd'] for r in usage)/1e6},notes=['Frozen read-only checkpoint, not an event shutdown. Remaining workers may continue after this timestamp.','Message and tool evidence is restricted to this event. Wallet balances are cumulative across runs.','USD values are estimated API equivalents, not cash charges on the linked ChatGPT subscription.','A budget wrap-up turn ends the worker even without an explicit end choice. Each call reserves $1.90, and a protected reserve can trigger wrap-up while a positive balance remains.','Unknown ledger entries retain holds. Saved provider usage is shown separately and was not reconciled by this export.','No questionnaire, agent restart, model call or allowance change was requested by this checkpoint export.'])
    encoded = json.dumps(data,ensure_ascii=False,separators=(',',':')).encode()
    destination=pathlib.Path(destination); destination.parent.mkdir(parents=True,exist_ok=True); destination.write_bytes(encoded); destination.chmod(0o600)
    print(json.dumps({'file':str(destination),'sha256':hashlib.sha256(encoded).hexdigest(),'bytes':len(encoded),'event':event,'messages':len(messages),'counts':counts,'usage':data['usage']}))

if __name__=='__main__': export(sys.argv[1])
