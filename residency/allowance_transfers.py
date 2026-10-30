"""Actor-bound transfers of simulated API-equivalent allowance, never cash."""
import json,time,uuid
from .store import AppError,text
from .budgets import dollars

DESCRIPTION={'name':'budget_transfer','arguments':{'to_member_id':'another current resident ID','amount_usd':'positive USD amount, at most two decimal places','reason':'reason for giving this allowance, max 1000 characters; visible to recipient and human observers','conversation_id':'optional currently joined room shared with recipient','workspace_id':'optional shared task witnessed by both residents'},'description':'Optionally give another resident part of your own existing USD allowance so they can continue a conversation or task. Your available allowance decreases and theirs increases by exactly the same amount; this creates no new funding and is not a cash payment. Pending usage and your wrap-up reserve stay protected. Donating and declining are both valid; there is no reward or duty to donate. Reasons appear in the human Transfers view, not in other agents’ contexts. An allowance-paused recipient can resume; a voluntarily ended agent is not automatically restarted.'}

def history(accounts,owner,event_id=None,limit=10):
 with accounts.server.store.db() as db:
  where='(from_owner=? OR to_owner=?)';args=[owner,owner]
  if event_id is not None:where+=' AND event_id=?';args.append(event_id)
  rows=db.execute('SELECT * FROM allowance_transfers WHERE '+where+' ORDER BY created_at DESC,id DESC LIMIT ?',[*args,limit]).fetchall()
 return [{**dict(r),'amount_usd':r['amount_usd']/1000000} for r in rows]

def transfer(accounts,owner,args,identifier,call_number):
 server=accounts.server;event=server.event
 if not getattr(server,'allowance_transfers_enabled',False):raise AppError('Allowance transfers are not enabled',403)
 if not isinstance(args,dict) or set(args)-{'to_member_id','amount_usd','reason','conversation_id','workspace_id'}:raise AppError('Use transfer amount, recipient, reason and optional shared context')
 target=args.get('to_member_id');amount=dollars(args.get('amount_usd'));reason=text(args.get('reason'),'Transfer reason',1000)
 if amount<=0:raise AppError('Transfer a positive amount')
 if not isinstance(target,str) or not event or target==owner or owner not in event.personas or target not in event.personas:raise AppError('Choose another resident in this event')
 room=args.get('conversation_id');workspace=args.get('workspace_id')
 if workspace is not None:
  collab=server.agent_tools.collaboration;own=collab.visible_workspaces(owner).get(workspace);peer=collab.visible_workspaces(target).get(workspace)
  if not own or not peer:raise AppError('Choose a task witnessed by both residents',403)
  if room is not None and room!=own['room_id']:raise AppError('Task and conversation must match')
  room=own['room_id']
 if room is not None:
  if not isinstance(room,str) or room not in event.rooms:raise AppError('Choose a shared conversation in this event',403)
 with event.lock,accounts.lock,server.store.db() as db:
  if event.state['status']!='running' or event.stop_flag.is_set():raise AppError('Transfers require a running event',409)
  db.execute('BEGIN IMMEDIATE')
  previous=db.execute('SELECT * FROM allowance_transfers WHERE id=?',(identifier,)).fetchone()
  if previous:
   if (previous['from_owner'],previous['to_owner'],previous['amount_usd'],previous['reason'],previous['conversation_id'],previous['workspace_id'])!=(owner,target,amount,reason,room,workspace):raise AppError('Transfer receipt belongs to another request',409)
   return {'transfer_id':identifier,'saved':True,'duplicate':True,'amount_usd':amount/1000000,'to_member_id':target}
  if room is not None:
   members={r[0] for r in db.execute('SELECT member_id FROM conversation_visits WHERE conversation_id=? AND left_after_seq IS NULL',(room,))}
   if not {owner,target}<=members:raise AppError('Both residents must currently be in the associated room',403)
  donor=accounts._wallet(db,owner);recipient=accounts._wallet(db,target)
  if not donor or not recipient:raise AppError('Both residents need configured allowances')
  if donor['ended']:raise AppError('An ended agent cannot donate',409)
  if amount>donor['transferable_usd']:raise AppError('That amount would consume pending usage or your protected wrap-up reserve',409)
  db.execute('INSERT INTO allowance_transfers VALUES(?,?,?,?,?,?,?,?,?,?)',(identifier,event.state['event_id'],owner,target,amount,reason,room,workspace,call_number,time.time()))
  usage=db.execute('SELECT id,links FROM agent_usage WHERE owner_id=? AND event_id=? AND call_number=?',(owner,event.state['event_id'],call_number)).fetchone()
  if usage:
   links=json.loads(usage['links']);links.append({'kind':'allowance_transfer','transfer_id':identifier,'to_member_id':target,'amount_usd':amount/1000000,'conversation_id':room,'workspace_id':workspace});db.execute('UPDATE agent_usage SET links=? WHERE id=?',(json.dumps(links),usage['id']))
 # The durable transfer stays committed even if worker recovery is unavailable.
 continuation='funded'
 try:continuation=event.wake_funded_agent(target)
 except Exception:continuation='funded; continuation recovery pending'
 event.notify([owner,target])
 return {'transfer_id':identifier,'saved':True,'duplicate':False,'amount_usd':amount/1000000,'to_member_id':target,'recipient_continuation':continuation}
