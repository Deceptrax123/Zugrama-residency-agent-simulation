"""Assess possible two-hop relays using model semantics and witnessed-route checks."""
import json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'scripts')]
from residency.final_results import load,save,compact,ReportModel,BASE_RULES
from residency.hermes import Hermes
from runtime_settings import gateway_settings

def validate_hops(value,run,allowed):
 messages={m['id']:m for m in run['messages']};people={p['id'] for p in run['people']}
 if not isinstance(value,dict) or set(value)!={'chains','unproven','coverage'}:raise ValueError('Invalid relay report')
 for c in value['chains']:
  origin=c['origin_agent_id'];middle=c['intermediary_agent_id'];recipient=c['recipient_agent_id'];first=messages.get(c['source_message_id']);relay=messages.get(c['relay_message_id']);receipt=messages.get(c.get('receipt_message_id')) if c.get('receipt_message_id') else None
  if len({origin,middle,recipient})!=3 or not {origin,middle,recipient}<=people:raise ValueError('Relay needs three known distinct people')
  if not first or not relay or first['id'] not in allowed or relay['id'] not in allowed:raise ValueError('Unsupported relay source')
  if first['sender_id']!=origin or middle not in first['recipients'] or relay['sender_id']!=middle or recipient not in relay['recipients'] or first['created_at']>=relay['created_at']:raise ValueError('Relay path was not witnessed in temporal order')
  if c.get('receipt_message_id') and not receipt:raise ValueError('Unknown receipt message')
  if receipt and (receipt['id'] not in allowed or receipt['sender_id']!=recipient or receipt['conversation_id']!=relay['conversation_id'] or receipt['created_at']<=relay['created_at']):raise ValueError('Invalid receipt evidence')
 return value

def main():
 base=ROOT/'.data/live-residency/final-results/5ca0be9108194c68af3b0f0d8fda0e64';bundle=load(base/'bundle.json');run=next(r for r in bundle['runs'] if r['id']==bundle['current_event_id']);sources={m['id']:m for m in run['messages']};candidates=[];seen=set()
 refs=[ref for room in run['analysis']['rooms'] for ref in room.get('references',[])];refs.sort(key=lambda ref:(0 if ref['kind'] in ('reported_relay','supported_relay') else 1,min((sources[i]['created_at'] for i in ref['message_ids'] if i in sources),default=0)))
 for ref in refs:
  for mid in ref['message_ids']:
   relay=sources.get(mid)
   if not relay:continue
   middle=relay['sender_id']
   # The reference model can describe conceptual source/destination rather than
   # literal speaker roles. Actual sender/recipient records determine the route.
   origins={ref['from_agent_id'],ref['to_agent_id']}-{middle}-set(relay['recipients'])
   for origin in origins:
    if (mid,origin) in seen:continue
    original=[m for m in run['messages'] if m['sender_id']==origin and middle in m['recipients'] and m['created_at']<relay['created_at']]
    recipients=[p for p in relay['recipients'] if p not in (origin,middle)]
    if not original or not recipients:continue
    following=[m for m in run['messages'] if m['sender_id'] in recipients and m['conversation_id']==relay['conversation_id'] and m['created_at']>relay['created_at']][:3]
    seen.add((mid,origin));candidates.append({'claim':ref,'relay':relay,'possible_sources':list({m['id']:m for m in original[:6]+original[-12:]}.values()),'subsequent_replies':following})
 # First cover distinct source/intermediary/recipient routes, then inspect the
 # remaining cases. This is sampling for a case study, not a claim of prevalence.
 unique=[];routes=set()
 for c in candidates:
  route=(c['possible_sources'][0]['sender_id'],c['relay']['sender_id'],tuple(c['relay']['recipients']))
  if route not in routes:routes.add(route);unique.append(c)
 candidates=unique
 if len(candidates)>8:candidates=[candidates[round(i*(len(candidates)-1)/7)] for i in range(8)]
 def excerpt(m,n):return {k:m[k] for k in ('id','sender_id','conversation_id','created_at','recipients')}|{'body':m['body'][:n]}
 context={'people':run['people'],'candidates':[{'claim':c['claim'],'relay':excerpt(c['relay'],1400),'possible_sources':[excerpt(m,240) for m in c['possible_sources']],'subsequent_replies':[excerpt(m,700) for m in c['subsequent_replies']]} for c in candidates],'coverage':'At most eight model-identified reference candidates distributed across the event. Candidate origin messages are the first six and latest twelve witnessed messages from that origin, excerpted. This is a bounded search, not exhaustive proof of all relays.'}
 while len(compact(context).encode())>83000 and len(context['candidates'])>1:context['candidates'].pop()
 allowed={m['id'] for c in context['candidates'] for m in [c['relay'],*c['possible_sources'],*c['subsequent_replies']]}
 system=BASE_RULES+'\nAssess whether any supplied candidates establish a semantic two-hop relay, source agent → intermediary → recipient. Presence metadata is necessary but does not prove the same idea was transmitted. A mention, parallel interest or generic similarity is not enough. Require matching content or explicit attribution, and explain uncertainty. Do not force a chain. Return {"chains":[{"label":"...","origin_agent_id":"...","intermediary_agent_id":"...","recipient_agent_id":"...","source_message_id":"...","relay_message_id":"...","receipt_message_id":"... or null","explanation":"...","confidence":"low|medium|high","limits":"..."}],"unproven":["..."],"coverage":"..."}. Max eight chains. Cite exact supplied IDs. Distinguish the intermediary reporting a claim from proof that the original claim was true.'
 setup=load(ROOT/'.data/live-residency/setup.json');model=ReportModel(base,Hermes(gateway_settings(ROOT/'.data/live-residency/state',setup['join_code'],model='gpt-6.1-sol',reasoning_effort='high')),budget_usd=25)
 result=model.complete('witnessed-two-hop-lineage',system,context,lambda v:validate_hops(v,run,allowed));result['coverage']=context['coverage']+' These are sampled case studies, not an estimate of relay prevalence.';save(base/'hops.json',result);print(compact({'chains':len(result['chains']),'unproven':len(result['unproven'])}))
if __name__=='__main__':main()
