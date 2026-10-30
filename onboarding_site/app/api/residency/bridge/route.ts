import {env} from 'cloudflare:workers';
import {bridgeAccess} from '../../../../lib/residency-access';
import {reply,failure,boundedBody} from '../../../../lib/api';
import {snapshotOwners} from '../../../../lib/residency-snapshot';
export async function POST(request:Request){try{
 bridgeAccess(request);const raw=JSON.parse(new TextDecoder().decode(await boundedBody(request,4000000)));
 if(raw.action==='heartbeat'){
  await env.DB!.prepare("UPDATE residency_snapshots SET updated_at=? WHERE owner_id='host'").bind(Date.now()).run();return reply({saved:true});
 }
 if(raw.action==='publish'){
  const retained=snapshotOwners(raw.snapshots,raw.owners);
  const owners=new Set<string>();const now=Date.now();const statements=[];
  for(const entry of raw.snapshots){
   if(!entry||typeof entry.owner_id!=='string'||(entry.owner_id!=='host'&&!/^anonymous:[0-9a-f]{64}$/.test(entry.owner_id))||owners.has(entry.owner_id))throw Error('Provide unique enrolled owners.');
   owners.add(entry.owner_id);const data=JSON.stringify(entry.data);if(!entry.data||data.length>900000)throw Error('Keep each residency view below 900,000 characters.');
   if(entry.owner_id!=='host'&&!await env.DB!.prepare('SELECT 1 AS found FROM submissions WHERE user_id=?').bind(entry.owner_id).first())continue;
   statements.push(env.DB!.prepare('INSERT INTO residency_snapshots(owner_id,data,updated_at) VALUES(?,?,?) ON CONFLICT(owner_id) DO UPDATE SET data=excluded.data,updated_at=excluded.updated_at').bind(entry.owner_id,data,now));
  }
  const ids=retained;statements.push(ids.length?env.DB!.prepare('DELETE FROM residency_snapshots WHERE owner_id NOT IN ('+ids.map(()=>'?').join(',')+')').bind(...ids):env.DB!.prepare('DELETE FROM residency_snapshots'));
  await env.DB!.batch(statements);return reply({saved:true,updated_at:now});
 }
 if(raw.action==='claim'){
  await env.DB!.prepare("UPDATE residency_commands SET status='failed',result=?,completed_at=? WHERE owner_id='host' AND status='queued' AND created_at<?").bind(JSON.stringify({error:'Host control expired before delivery. No event was started; submit it again when connected.'}),Date.now(),Date.now()-60000).run();
  await env.DB!.prepare("UPDATE residency_commands SET status='uncertain',result=?,completed_at=? WHERE status='processing' AND claimed_at<?").bind(JSON.stringify({error:'Bridge acknowledgement was interrupted; execution is uncertain. No automatic retry.'}),Date.now(),Date.now()-600000).run();
  const lease=crypto.randomUUID();const job=await env.DB!.prepare("UPDATE residency_commands SET status='processing',claimed_at=?,lease_token=? WHERE id=(SELECT id FROM residency_commands WHERE status='queued' ORDER BY created_at,id LIMIT 1) AND status='queued' RETURNING id,owner_id,kind,payload,lease_token,created_at").bind(Date.now(),lease).first();
  return reply({job:job?{...job,payload:JSON.parse(job.payload as string)}:null});
 }
 if(raw.action==='complete'){
  if(typeof raw.id!=='string'||typeof raw.lease_token!=='string'||!['completed','failed','uncertain'].includes(raw.status)||!raw.result||JSON.stringify(raw.result).length>12000)throw Error('Provide a bounded leased result.');
  const result=await env.DB!.prepare("UPDATE residency_commands SET status=?,result=?,completed_at=? WHERE id=? AND lease_token=? AND status='processing'").bind(raw.status,JSON.stringify(raw.result),Date.now(),raw.id,raw.lease_token).run();
  return reply({saved:result.meta.changes===1});
 }
 throw Error('Unknown bridge action.');
}catch(error){return failure(error);}}
