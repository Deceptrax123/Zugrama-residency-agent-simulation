import type {Board,Shape} from '../components/agent-workspace';
export type WatchArtifact={id:string,kind:'python'|'board'|'workspace'|'transfer',owner_id:string,room_id:string|null,created_at:number,data:Record<string,unknown>,seq?:number};
const str=(x:unknown,max:number)=>{if(typeof x!=='string'||x.length>max)throw Error('Invalid artifact text.');return x;};
const num=(x:unknown)=>{if(typeof x!=='number'||!Number.isFinite(x)||x<0)throw Error('Invalid artifact number.');return x;};
export function projectArtifact(raw:unknown):WatchArtifact{
 if(!raw||typeof raw!=='object')throw Error('Provide an artifact.');const r=raw as Record<string,unknown>,d=r.data as Record<string,unknown>;if(!d||typeof d!=='object')throw Error('Provide artifact content.');let data:Record<string,unknown>;
 if(r.kind==='python')data={code:str(d.code,16000),status:str(d.status,30),call_number:num(d.call_number),stdout:str(d.stdout||'',12000),output:str(d.output||'',30000),error:str(d.error||'',2000)};
 else if(r.kind==='board'){
  if(!Array.isArray(d.equations)||d.equations.length>12||!Array.isArray(d.shapes)||d.shapes.length>30)throw Error('Invalid board collections.');
  const shapes=d.shapes.map(s=>{if(!s||!['line','circle','rect','text'].includes(s.type))throw Error('Invalid shape.');const out:Record<string,unknown>={type:s.type};for(const k of ['x','y','x2','y2','r','width','height'])if(s[k]!==undefined){out[k]=num(s[k]);if((out[k] as number)>1000)throw Error('Invalid coordinate.');}if(s.text!==undefined)out.text=str(s.text,160);return out as Shape;});
  data={title:str(d.title,120),text:str(d.text,8000),equations:d.equations.map(e=>str(e,1000)),shapes,message_id:str(d.message_id,100)};
 }else if(r.kind==='workspace')data={workspace_id:str(d.workspace_id,100),title:str(d.title,120),state:str(d.state,12000),revision:num(d.revision),status:str(d.status,30),message_id:str(d.message_id,100)};
 else if(r.kind==='transfer'){const amount=num(d.amount_usd);if(amount<=0||amount>10000||Math.abs(amount*100-Math.round(amount*100))>0.00001)throw Error('Invalid transfer amount.');data={recipient_id:str(d.recipient_id,100),amount_usd:num(d.amount_usd),reason:str(d.reason,1000),workspace_id:d.workspace_id===null?null:str(d.workspace_id,100),call_number:num(d.call_number)};}
 else throw Error('Only code, boards, shared workspaces and allowance transfers are published.');
 return {id:str(r.id,150),kind:r.kind,owner_id:str(r.owner_id,100),room_id:r.room_id===null?null:str(r.room_id,100),created_at:num(r.created_at),data};
}
export function validateArtifacts(raw:unknown){if(!Array.isArray(raw)||raw.length>20)throw Error('Upload at most twenty artifacts.');return raw.map(projectArtifact);}
export function artifactBoard(a:WatchArtifact):Board{return {id:a.id,owner_id:a.owner_id,room_id:a.room_id||'',created_at:a.created_at,...a.data} as Board;}
