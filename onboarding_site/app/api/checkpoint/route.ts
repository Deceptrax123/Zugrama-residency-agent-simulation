import {env} from 'cloudflare:workers';
import {boundedBody,reply} from '../../../lib/api';
import {checkpointKey,hostAuthorized,validateCheckpoint} from '../../../lib/checkpoint';
export const dynamic='force-dynamic';
export async function GET(request:Request){
 if(!hostAuthorized(request,env.RESIDENCY_HOST_TOKEN))return reply({error:'Private host access required.'},401);
 const bucket=env.BUCKET;if(!bucket)return reply({error:'Checkpoint storage unavailable.'},503);
 const object=await bucket.get(checkpointKey);
 if(!object)return reply({error:'The checkpoint has not been uploaded yet.'},404);
 return new Response(object.body,{headers:{'Content-Type':'application/json','Cache-Control':'no-store','Referrer-Policy':'no-referrer','X-Content-Type-Options':'nosniff'}});
}
export async function POST(request:Request){
 if(!hostAuthorized(request,env.RESIDENCY_HOST_TOKEN))return reply({error:'Private host access required.'},401);
 if(request.headers.get('origin')!==new URL(request.url).origin)return reply({error:'Use this site origin.'},403);
 const bucket=env.BUCKET;if(!bucket)return reply({error:'Checkpoint storage unavailable.'},503);
 let bytes:Uint8Array;let parsed:unknown;
 try{bytes=await boundedBody(request,5000000);parsed=JSON.parse(new TextDecoder().decode(bytes));}catch(e){if(e instanceof Response)return e;return reply({error:'Invalid checkpoint JSON.'},400);}
 if(!validateCheckpoint(parsed))return reply({error:'Invalid checkpoint schema.'},400);
 const digest=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',new Uint8Array(bytes).buffer))).map(b=>b.toString(16).padStart(2,'0')).join('');
 const existing=await bucket.head(checkpointKey);
 if(existing)return reply(existing.customMetadata?.sha256===digest?{saved:true,unchanged:true,sha256:digest}:{error:'This checkpoint is frozen and cannot be replaced.'},existing.customMetadata?.sha256===digest?200:409);
 const saved=await bucket.put(checkpointKey,bytes,{onlyIf:{etagDoesNotMatch:'*'},httpMetadata:{contentType:'application/json'},customMetadata:{sha256:digest}});
 if(!saved)return reply({error:'A checkpoint was uploaded concurrently. Retry the same file.'},409);
 return reply({saved:true,sha256:digest},201);
}
