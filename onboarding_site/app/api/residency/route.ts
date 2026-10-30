import {env} from 'cloudflare:workers';
import {reply,failure,boundedBody} from '../../../lib/api';
import {residencyActor} from '../../../lib/residency-access';
import {commandPayload} from '../../../lib/residency-command';
export async function GET(request:Request){try{
 const actor=await residencyActor(request);const snapshot=await env.DB!.prepare('SELECT data,updated_at FROM residency_snapshots WHERE owner_id=?').bind(actor).first<{data:string,updated_at:number}>();
 const heartbeat=await env.DB!.prepare("SELECT updated_at FROM residency_snapshots WHERE owner_id='host'").first<{updated_at:number}>();
 const commands=await env.DB!.prepare('SELECT id,kind,payload,status,created_at,result FROM residency_commands WHERE owner_id=? ORDER BY created_at DESC LIMIT 30').bind(actor).all();
 return reply({snapshot:snapshot?JSON.parse(snapshot.data):null,updated_at:snapshot?.updated_at||null,heartbeat_at:heartbeat?.updated_at||null,commands:commands.results.map(row=>({...row,payload:JSON.parse(row.payload as string),result:row.result?JSON.parse(row.result as string):null}))});
}catch(error){return failure(error);}}
export async function POST(request:Request){try{
 const actor=await residencyActor(request,true);const raw=JSON.parse(new TextDecoder().decode(await boundedBody(request,16000)));
 const snapshot=await env.DB!.prepare('SELECT data,updated_at FROM residency_snapshots WHERE owner_id=?').bind(actor).first<{data:string,updated_at:number}>();
 if(!snapshot)return reply({error:'Your reviewed introduction has not been enrolled yet.'},409);
 const view=JSON.parse(snapshot.data),command=commandPayload(actor,raw,view.directory||[],view.agent?.member_id);
 const duplicate=await env.DB!.prepare('SELECT id,status FROM residency_commands WHERE owner_id=? AND request_key=?').bind(actor,raw.request_id).first();
 if(duplicate)return reply(duplicate);
 const heartbeat=await env.DB!.prepare("SELECT updated_at FROM residency_snapshots WHERE owner_id='host'").first<{updated_at:number}>();
 if(!heartbeat||heartbeat.updated_at<Date.now()-90000)return reply({error:'The residency connection is offline. No request was queued; try again when it reconnects.'},503);
 const open=await env.DB!.prepare("SELECT count(*) AS count FROM residency_commands WHERE owner_id=? AND status IN ('queued','processing')").bind(actor).first<{count:number}>();
 if((open?.count||0)>=20)return reply({error:'Wait for pending requests to finish.'},429);
 const id=crypto.randomUUID();await env.DB!.prepare("INSERT INTO residency_commands(id,owner_id,request_key,kind,payload,status,created_at) VALUES(?,?,?,?,?,'queued',?) ON CONFLICT(owner_id,request_key) DO NOTHING").bind(id,actor,raw.request_id,command.kind,JSON.stringify(command.payload),Date.now()).run();
 const saved=await env.DB!.prepare('SELECT id,status FROM residency_commands WHERE owner_id=? AND request_key=?').bind(actor,raw.request_id).first();
 return reply(saved,202);
}catch(error){return failure(error);}}
