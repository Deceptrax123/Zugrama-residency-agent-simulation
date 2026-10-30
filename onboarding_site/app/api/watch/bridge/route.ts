import {env} from 'cloudflare:workers';
import {bridgeAccess} from '../../../../lib/residency-access';
import {boundedBody,reply,failure} from '../../../../lib/api';
import {projectWatchState,validateWatchMessages} from '../../../../lib/watch';
import {validateArtifacts} from '../../../../lib/watch-artifacts';
import {ensureWatchDb} from '../../../../lib/watch-db';
let initialized=false;
export async function POST(request:Request){try{
 bridgeAccess(request);if(!env.DB)return reply({error:'Watch storage unavailable.'},503);const db=env.DB;
 if(!initialized){await ensureWatchDb(db);initialized=true;}
 const raw=JSON.parse(new TextDecoder().decode(await boundedBody(request,1500000)));
 if(raw.action==='status'){
  if(typeof raw.event_id!=='string'||raw.event_id.length>100)throw Error('Choose an event.');
  const row=await db.prepare('SELECT coalesce(max(seq),0) AS last_seq,count(*) AS count FROM watch_messages WHERE event_id=?').bind(raw.event_id).first();return reply(row);
 }
 if(raw.action!=='publish')throw Error('Choose a bridge action.');
 const state=projectWatchState(raw.state),messages=validateWatchMessages(raw.messages),artifacts=validateArtifacts(raw.artifacts||[]);if(!state.event_id&&messages.length)throw Error('Messages require an event.');
 const rooms=new Set(state.rooms.map(r=>r.id));if(messages.some(m=>!rooms.has(m.conversation_id))||artifacts.some(a=>a.room_id!==null&&!rooms.has(a.room_id)))throw Error('Messages must belong to this event.');
 const statements=messages.map(m=>db.prepare('INSERT INTO watch_messages(event_id,id,seq,conversation_id,sender_id,body,created_at,recipients) VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(event_id,id) DO NOTHING').bind(state.event_id,m.id,m.seq,m.conversation_id,m.sender_id,m.body,m.created_at,JSON.stringify(m.recipients)));
 for(const a of artifacts)statements.push(db.prepare('INSERT INTO watch_artifacts(event_id,id,kind,owner_id,room_id,created_at,data) VALUES(?,?,?,?,?,?,?) ON CONFLICT(event_id,id) DO UPDATE SET data=excluded.data').bind(state.event_id,a.id,a.kind,a.owner_id,a.room_id,a.created_at,JSON.stringify(a.data)));
 statements.push(db.prepare("INSERT INTO watch_state(id,event_id,data,updated_at) VALUES('current',?,?,?) ON CONFLICT(id) DO UPDATE SET event_id=excluded.event_id,data=excluded.data,updated_at=excluded.updated_at").bind(state.event_id,JSON.stringify(state),Date.now()));statements.push(db.prepare('INSERT INTO watch_state(id,event_id,data,updated_at) VALUES(?,?,?,?) ON CONFLICT(id) DO UPDATE SET data=excluded.data,updated_at=excluded.updated_at').bind('event:'+state.event_id,state.event_id,JSON.stringify(state),Date.now()));await db.batch(statements);return reply({saved:true,messages:messages.length});
}catch(e){return failure(e);}}
