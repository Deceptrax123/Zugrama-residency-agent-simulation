import {env} from 'cloudflare:workers';
import {reply,failure,boundedBody} from '../../../../lib/api';
import {bearer} from '../../../../lib/residency-access';
import {validSubmissionKey,submissionOwner} from '../../../../lib/submission-key';
import {createRecoveryCode,recoveryDigest,RECOVERY_LIFETIME_MS} from '../../../../lib/resident-recovery';
const invalid=()=>reply({error:'This recovery code is invalid, expired or already used. Ask the host for a new code.'},400);
export async function POST(request:Request){try{
 if(request.headers.get('Origin')!==new URL(request.url).origin)return reply({error:'Use recovery on this site.'},403);
 if(!request.headers.get('Content-Type')?.startsWith('application/json'))return reply({error:'Send recovery as JSON.'},415);
 const raw=JSON.parse(new TextDecoder().decode(await boundedBody(request,4096)));
 if(!raw||typeof raw!=='object'||Array.isArray(raw))throw Error('Choose a recovery action.');
 if(raw.action==='issue'){
  if(!bearer(request,env.RESIDENCY_HOST_TOKEN))return reply({error:'Host authorization required.'},401);
  if(Object.keys(raw).some(k=>!['action','member_id'].includes(k))||typeof raw.member_id!=='string'||!raw.member_id||raw.member_id.length>100)throw Error('Choose an enrolled resident.');
  // Resolve the local agent ID on the server. Names and supplied owner IDs never
  // select a private identity, and neither the bridge nor resident keys can issue.
  const row=await env.DB!.prepare("SELECT s.owner_id FROM residency_snapshots s JOIN submissions p ON p.user_id=s.owner_id WHERE s.owner_id LIKE 'anonymous:%' AND json_extract(s.data,'$.role')='resident' AND json_extract(s.data,'$.agent.member_id')=?")
   .bind(raw.member_id).all<{owner_id:string}>();
  if(row.results.length!==1||!/^anonymous:[a-f0-9]{64}$/.test(row.results[0].owner_id))return reply({error:'This resident is not enrolled in the hosted dashboard.'},404);
  const code=createRecoveryCode(),hash=await recoveryDigest(code),now=Date.now(),expires=now+RECOVERY_LIFETIME_MS;
  await env.DB!.prepare('INSERT INTO resident_recovery_codes(owner_id,code_hash,created_at,expires_at,used_at) VALUES(?,?,?,?,NULL) ON CONFLICT(owner_id) DO UPDATE SET code_hash=excluded.code_hash,created_at=excluded.created_at,expires_at=excluded.expires_at,used_at=NULL')
   .bind(row.results[0].owner_id,hash,now,expires).run();
  return reply({code,expires_at:expires});
 }
 if(raw.action==='redeem'){
  if(Object.keys(raw).some(k=>!['action','code','access_key'].includes(k))||!validSubmissionKey(raw.access_key))return invalid();
  const hash=await recoveryDigest(raw.code),accessHash=await submissionOwner(raw.access_key),now=Date.now();
  // D1 batch is transactional: only one concurrent redemption can insert a key
  // and consume the code. Never alias an existing original submission key.
  const result=await env.DB!.batch([
   env.DB!.prepare('INSERT INTO resident_access_keys(access_hash,owner_id,created_at) SELECT ?,c.owner_id,? FROM resident_recovery_codes c JOIN submissions p ON p.user_id=c.owner_id WHERE c.code_hash=? AND c.used_at IS NULL AND c.expires_at>? AND NOT EXISTS(SELECT 1 FROM submissions WHERE user_id=?) AND NOT EXISTS(SELECT 1 FROM resident_access_keys WHERE access_hash=?)')
    .bind(accessHash,now,hash,now,accessHash,accessHash),
   env.DB!.prepare('UPDATE resident_recovery_codes SET used_at=? WHERE code_hash=? AND used_at IS NULL AND expires_at>? AND EXISTS(SELECT 1 FROM resident_access_keys k WHERE k.access_hash=? AND k.owner_id=resident_recovery_codes.owner_id AND k.created_at=?)')
    .bind(now,hash,now,accessHash,now),
  ]);
  if(result[0].meta.changes!==1||result[1].meta.changes!==1)return invalid();
  return reply({restored:true});
 }
 throw Error('Choose a recovery action.');
}catch(error){return failure(error);}}
