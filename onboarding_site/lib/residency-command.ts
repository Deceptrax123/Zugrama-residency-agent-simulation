export function commandPayload(actor:string,input:unknown,directory:{id:string}[],ownId?:string){
 const raw=input as Record<string,unknown>;
 if(!raw||typeof raw!=='object'||Array.isArray(raw)||Object.keys(raw).some(k=>!['kind','request_id','body','target_id','max_calls','npc_enabled','seven_days','confirmed'].includes(k)))throw Error('Provide a residency request.');
 if(typeof raw.request_id!=='string'||!/^[A-Za-z0-9_-]{16,80}$/.test(raw.request_id))throw Error('Provide a unique request ID.');
 if(actor==='host'){
  if(!['start','stop','sleep','next','resume','analyze'].includes(raw.kind as string))throw Error('Choose a host event control.');
  if(raw.kind==='start'){
   const limit=raw.max_calls??null;
   if(raw.confirmed!==true||(limit!==null&&(!Number.isInteger(limit)||Number(limit)<1||Number(limit)>60))||typeof raw.npc_enabled!=='boolean'||typeof raw.seven_days!=='boolean')throw Error('Confirm Start and choose valid event options.');
   return {kind:'start',payload:{max_calls:limit,npc_enabled:raw.npc_enabled,seven_days:raw.seven_days}};
  }
  if(['resume','analyze'].includes(raw.kind as string)&&raw.confirmed!==true)throw Error('Confirm this host action.');
  return {kind:raw.kind as string,payload:{}};
 }
 if(raw.kind!=='request'||typeof raw.body!=='string'||!raw.body.trim()||raw.body.length>4000||raw.body.includes('\0'))throw Error('Write a request to your own agent, up to 4,000 characters.');
 const target=raw.target_id??null;
 if(target!==null&&(typeof target!=='string'||target===ownId||!directory.some(p=>p.id===target)))throw Error('Choose another enrolled resident, or leave the target open.');
 return {kind:'request',payload:{body:raw.body.trim(),target_id:target}};
}
