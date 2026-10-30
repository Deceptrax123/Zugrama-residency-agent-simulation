import {env} from 'cloudflare:workers';
import {reply,failure} from '../../../lib/api';
import {WATCH_CONFIG_KEY,watchDigest,equalDigest,projectWatchState,type WatchMessage} from '../../../lib/watch';
import {projectArtifact} from '../../../lib/watch-artifacts';
export const dynamic='force-dynamic';
export async function GET(request:Request){try{
 const supplied=await watchDigest(request.headers.get('X-Watch-Code'));if(!supplied)return reply({error:'Enter the shared residency code.'},401);
 const config=await env.BUCKET?.get(WATCH_CONFIG_KEY);if(!config)return reply({error:'The shared live screen is not configured yet.'},503);
 const access=await config.json() as {digest:string,enabled:boolean};if(!access.enabled||!equalDigest(supplied,access.digest))return reply({error:'That shared code is not valid. Ask the host for the current code.'},401);
 const chosen=new URL(request.url).searchParams.get('event');if(chosen!==null&&!/^[A-Za-z0-9_-]{1,100}$/.test(chosen))throw Error('Choose a valid event.');
 const row=await env.DB!.prepare("SELECT event_id,data,updated_at FROM watch_state WHERE id=?").bind(chosen?'event:'+chosen:'current').first<{event_id:string,data:string,updated_at:number}>();
 if(!row&&chosen)return reply({error:'Event not found.'},404);
 if(!row)return reply({state:null,messages:[],synced_messages:0,updated_at:null,has_older:false});
 const state=projectWatchState(JSON.parse(row.data)),url=new URL(request.url),room=url.searchParams.get('room'),before=url.searchParams.get('before'),after=url.searchParams.get('after');
 const kind=url.searchParams.get('artifacts');
 if(kind!==null){
  if(!['all','python','board','workspace','transfer'].includes(kind))throw Error('Choose an artifact type.');
  const params:(string|number)[]=[row.event_id];let where='event_id=?';
  if(kind!=='all'){where+=' AND kind=?';params.push(kind);}
  if(room){if(!state.rooms.some(r=>r.id===room))return reply({error:'Conversation not found.'},404);where+=' AND room_id=?';params.push(room);}
  const owner=url.searchParams.get('owner');if(owner){if(kind==='transfer'){where+=" AND (owner_id=? OR json_extract(data,'$.recipient_id')=?)";params.push(owner,owner);}else{where+=' AND owner_id=?';params.push(owner);}}
  if(before!==null){const n=Number(before);if(!/^\d+$/.test(before)||!Number.isSafeInteger(n)||n<0)throw Error('Invalid artifact cursor.');where+=' AND seq<?';params.push(n);}
  const result=await env.DB!.prepare('SELECT seq,id,kind,owner_id,room_id,created_at,data FROM watch_artifacts WHERE '+where+' ORDER BY seq DESC LIMIT 11').bind(...params).all();
  const artifacts=result.results.slice(0,10).map(a=>({...projectArtifact({...a,data:JSON.parse(a.data as string)}),seq:a.seq}));
  return reply({event_id:row.event_id,artifacts,has_older:result.results.length>10,updated_at:row.updated_at});
 }
 if(before&&after)throw Error('Use one message cursor.');const params:(string|number)[]=[row.event_id];let where='event_id=?';
 if(room){if(!state.rooms.some(r=>r.id===room))return reply({error:'Conversation not found.'},404);where+=' AND conversation_id=?';params.push(room);}
 for(const [key,value] of [['before',before],['after',after]] as const){if(value!==null){const n=Number(value);if(!/^\d+$/.test(value)||!Number.isSafeInteger(n)||n<0)throw Error('Invalid message cursor.');where+=' AND seq'+(key==='before'?'<':'>')+'?';params.push(n);}}
 const ascending=after!==null;const result=await env.DB!.prepare('SELECT id,seq,conversation_id,sender_id,body,created_at,recipients FROM watch_messages WHERE '+where+' ORDER BY seq '+(ascending?'ASC':'DESC')+' LIMIT 81').bind(...params).all();
 const has_more=result.results.length>80,selected=result.results.slice(0,80),messages=selected.map(m=>({...m,recipients:JSON.parse(m.recipients as string)})) as WatchMessage[];if(!ascending)messages.reverse();
 const total=await env.DB!.prepare('SELECT count(*) AS count FROM watch_messages WHERE event_id=?').bind(row.event_id).first<{count:number}>();
 const archive=await env.DB!.prepare("SELECT event_id,data FROM watch_state WHERE id LIKE 'event:%' ORDER BY updated_at DESC LIMIT 50").all();
 const events=archive.results.map(r=>{const s=projectWatchState(JSON.parse(r.data as string));return {event_id:s.event_id,status:s.status,started_at:s.started_at,message_count:s.message_count};}).sort((a,b)=>(b.started_at||0)-(a.started_at||0));
 const current=await env.DB!.prepare("SELECT event_id FROM watch_state WHERE id='current'").first<{event_id:string}>();
 return reply({state,events,current_event_id:current?.event_id,messages,synced_messages:total?.count||0,updated_at:row.updated_at,has_older:!ascending&&has_more,has_more:ascending&&has_more});
}catch(e){return failure(e);}}
