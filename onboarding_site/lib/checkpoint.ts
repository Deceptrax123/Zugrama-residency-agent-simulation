export const checkpointSlug='continuation-2026-10-29';
export const checkpointKey='reports/checkpoints/'+checkpointSlug+'.json';
export type Message={id:string,conversation_id:string,sender_id:string,body:string,created_at:number,seq:number,recipients:string[]};
export type Agent={id:string,name:string,classification:string,error:string|null,calls:number,messages:number,last_message_ids:string[],budget:{limit_usd:number,reserve_usd:number,spent_usd:number,held_usd:number,remaining_usd:number,ended:boolean},last:null|{call_number:number,purpose:string,status:string,created_at:number,decision:{budget_choice?:string,wait_seconds?:number,messages?:unknown[]},provider_usage:unknown,audit_response_saved:boolean,produced_ids:string[]}};
export type Checkpoint={schema_version:number,slug:string,title:string,captured_at:number,event:{event_id:string,status:string,started_at:number,calls:number,completed_calls:number,message_count:number,protocol:string},counts:Record<string,number>,agents:Agent[],messages:Message[],tools:{id:string,owner_id:string,call_number:number,name:string,result:unknown,status:string,created_at:number}[],boards:{id:string,owner_id:string,message_id:string,body:string,created_at:number}[],usage:{requests:number,recorded_requests:number,unknown_requests:number,rejected_requests:number,tokens:number,estimated_usd:number},notes:string[],findings?:{title:string,summary:string,message_ids:string[],tool_ids:string[]}[]};
export const endingLabels:Record<string,string>={budget_wrap_up:'Budget wrap-up',explicit_end:'Chose to end',ended_before_run:'Ended before this run',budget_paused:'No available allowance',worker_error:'Worker error',remaining_worker:'Remaining worker',ended_unexplained:'Unexplained ending'};
export function hostAuthorized(request:Request,secret?:string){
 const expected='Bearer '+secret,actual=request.headers.get('authorization')||'';let mismatch=actual.length^expected.length;
 for(let i=0;i<expected.length;i++)mismatch|=expected.charCodeAt(i)^(actual.charCodeAt(i)||0);
 return !!secret&&!mismatch;
}
export function validateCheckpoint(value:unknown):value is Checkpoint{
 if(!value||typeof value!=='object')return false;const d=value as Checkpoint;
 return d.schema_version===1&&d.slug===checkpointSlug&&typeof d.title==='string'&&Number.isFinite(d.captured_at)&&!!d.event&&typeof d.event.event_id==='string'&&Number.isFinite(d.event.started_at)&&Array.isArray(d.agents)&&d.agents.length>0&&d.agents.length<=50&&Array.isArray(d.messages)&&d.messages.length<=20000&&Array.isArray(d.tools)&&Array.isArray(d.boards)&&Array.isArray(d.notes)&&!!d.usage&&!!d.counts&&d.agents.every(a=>typeof a.id==='string'&&typeof a.name==='string'&&a.classification in endingLabels&&!!a.budget&&Array.isArray(a.last_message_ids))&&d.messages.every(m=>typeof m.id==='string'&&typeof m.body==='string'&&typeof m.sender_id==='string'&&typeof m.conversation_id==='string'&&Number.isFinite(m.created_at)&&m.created_at<=d.captured_at&&Array.isArray(m.recipients))&&new Set(d.messages.map(m=>m.id)).size===d.messages.length;
}
export function deliveryEdges(messages:Message[],end:number,window:number){
 const counts=new Map<string,{source:string,target:string,count:number}>();
 for(const m of messages){if(m.created_at>end||m.created_at<=end-window)continue;for(const target of new Set(m.recipients)){if(target===m.sender_id)continue;const key=m.sender_id+':'+target;const edge=counts.get(key)||{source:m.sender_id,target,count:0};edge.count++;counts.set(key,edge);}}
 return [...counts.values()];
}
