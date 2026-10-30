// Explicit observer projection: no identity documents, memories or commands.
export type WatchMessage={id:string,seq:number,conversation_id:string,sender_id:string,body:string,created_at:number,recipients:string[]};
export type MembershipChange={member_id:string,kind:'joined'|'left',at:number};
export type WatchState={new_additions?:{id:string,title:string,body:string,created_at:number}[],event_id:string|null,status:string,started_at:number|null,captured_at:number,message_count:number,completed_calls:number,thinking:string[],directory:{id:string,name:string,nickname:string,state:string}[],rooms:{id:string,participants:string[],message_count:number,last_at:number,last_seq:number,active_participants?:string[],peak_residents?:number,membership_changes?:MembershipChange[],membership_change_count?:number}[],tools:{owner_id:string,name:string,status:string,created_at:number}[]};
export const WATCH_CONFIG_KEY='live-watch/access-v1.json';
export function normalizeWatchCode(value:unknown){if(typeof value!=='string'||value.length>100)return null;const code=value.replace(/[\s-]/g,'').toUpperCase();return /^[A-Z2-7]{16}$/.test(code)?code:null;}
export async function watchDigest(value:unknown){const code=normalizeWatchCode(value);if(!code)return null;return Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',new TextEncoder().encode('zugrama-watch/v1:'+code)))).map(n=>n.toString(16).padStart(2,'0')).join('');}
export function equalDigest(a:string,b:string){let d=a.length^b.length;for(let i=0;i<a.length;i++)d|=a.charCodeAt(i)^(b.charCodeAt(i)||0);return !d;}
export function projectWatchState(raw:unknown):WatchState{
 if(!raw||typeof raw!=='object')throw Error('Provide a watch state.');const r=raw as Record<string,unknown>;
 const str=(x:unknown,max=100)=>{if(typeof x!=='string'||x.length>max)throw Error('Invalid watch text.');return x;};
 const num=(x:unknown)=>{if(typeof x!=='number'||!Number.isFinite(x)||x<0)throw Error('Invalid watch number.');return x;};
 if(!Array.isArray(r.directory)||r.directory.length>51||!Array.isArray(r.rooms)||r.rooms.length>5000||!Array.isArray(r.tools)||r.tools.length>30||!Array.isArray(r.thinking))throw Error('Invalid watch collections.');
 const additions=r.new_additions===undefined?[]:r.new_additions;if(!Array.isArray(additions)||additions.length>10)throw Error('Invalid event notices.');
 const directory=r.directory.map((p:Record<string,unknown>)=>({id:str(p.id),name:str(p.name,200),nickname:str(p.nickname||'',100),state:str(p.state,30)}));const ids=new Set(directory.map(p=>p.id));
 return {new_additions:additions.map((n:Record<string,unknown>)=>({id:str(n.id),title:str(n.title,160),body:str(n.body,2000),created_at:num(n.created_at)})),event_id:r.event_id===null?null:str(r.event_id),status:str(r.status,40),started_at:r.started_at===null?null:num(r.started_at),captured_at:num(r.captured_at),message_count:num(r.message_count),completed_calls:num(r.completed_calls),thinking:r.thinking.map(id=>{const p=str(id);if(!ids.has(p))throw Error('Unknown thinking resident.');return p;}),directory,
 rooms:r.rooms.map((p:Record<string,unknown>)=>{if(!Array.isArray(p.participants))throw Error('Invalid room.');
 const extras:Partial<WatchState['rooms'][number]>={};
 if(p.active_participants!==undefined){if(!Array.isArray(p.active_participants)||p.active_participants.length>51)throw Error('Invalid active membership.');extras.active_participants=p.active_participants.map(id=>str(id));}
 if(p.peak_residents!==undefined)extras.peak_residents=num(p.peak_residents);
 if(p.membership_changes!==undefined){if(!Array.isArray(p.membership_changes)||p.membership_changes.length>100)throw Error('Invalid membership history.');extras.membership_changes=p.membership_changes.map((c:Record<string,unknown>)=>{if(c.kind!=='joined'&&c.kind!=='left')throw Error('Invalid membership change.');return {member_id:str(c.member_id),kind:c.kind,at:num(c.at)};});extras.membership_change_count=num(p.membership_change_count);}
 return {id:str(p.id),participants:p.participants.map(id=>str(id)),message_count:num(p.message_count),last_at:num(p.last_at),last_seq:num(p.last_seq),...extras};}),
 tools:r.tools.map((p:Record<string,unknown>)=>({owner_id:str(p.owner_id),name:str(p.name,60),status:str(p.status,30),created_at:num(p.created_at)}))};
}
export function validateWatchMessages(value:unknown):WatchMessage[]{
 if(!Array.isArray(value)||value.length>40)throw Error('Upload at most forty messages.');
 return value.map(m=>{if(!m||typeof m.id!=='string'||m.id.length>100||!Number.isSafeInteger(m.seq)||m.seq<1||typeof m.conversation_id!=='string'||m.conversation_id.length>100||typeof m.sender_id!=='string'||m.sender_id.length>100||typeof m.body!=='string'||m.body.length>30000||typeof m.created_at!=='number'||!Number.isFinite(m.created_at)||!Array.isArray(m.recipients)||m.recipients.length>51||m.recipients.some((s:unknown)=>typeof s!=='string'||s.length>100))throw Error('Invalid conversation message.');return {id:m.id,seq:m.seq,conversation_id:m.conversation_id,sender_id:m.sender_id,body:m.body,created_at:m.created_at,recipients:[...new Set(m.recipients)] as string[]};});
}
