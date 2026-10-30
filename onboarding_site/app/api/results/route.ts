import {env} from 'cloudflare:workers';
import {reply,boundedBody} from '../../../lib/api';
import {RESULTS_KEY,validateResults} from '../../../lib/results';
import {WATCH_CONFIG_KEY,watchDigest,equalDigest} from '../../../lib/watch';
import {hostAuthorized} from '../../../lib/checkpoint';
export const dynamic='force-dynamic';
export async function GET(request:Request){
 let allowed=hostAuthorized(request,env.RESIDENCY_HOST_TOKEN);
 if(!allowed){const digest=await watchDigest(request.headers.get('X-Watch-Code'));const stored=await env.BUCKET?.get(WATCH_CONFIG_KEY);if(digest&&stored){const a=await stored.json() as {digest:string,enabled:boolean};allowed=a.enabled&&equalDigest(digest,a.digest);}}
 if(!allowed)return reply({error:'Use the shared residency code to open the results.'},401);
 const obj=await env.BUCKET?.get(RESULTS_KEY);if(!obj)return reply({error:'The frozen report is still being prepared.'},404);
 return new Response(obj.body,{headers:{'Content-Type':'application/json','Cache-Control':'no-store','X-Content-Type-Options':'nosniff','Referrer-Policy':'no-referrer'}});
}
export async function POST(request:Request){
 if(!hostAuthorized(request,env.RESIDENCY_HOST_TOKEN))return reply({error:'Host access required.'},401);
 if(request.headers.get('origin')!==new URL(request.url).origin)return reply({error:'Use this site origin.'},403);
 if(!env.BUCKET)return reply({error:'Storage unavailable.'},503);
 let bytes:Uint8Array,value:unknown;try{bytes=await boundedBody(request,30000000);value=JSON.parse(new TextDecoder().decode(bytes));}catch(e){if(e instanceof Response)return e;return reply({error:'Invalid report JSON.'},400);}
 if(!validateResults(value))return reply({error:'Invalid report or private fields in export.'},400);
 const old=await env.BUCKET.head(RESULTS_KEY);if(old&&old.customMetadata?.source_sha256!==value.source_sha256)return reply({error:'This report is pinned to a different frozen source.'},409);
 const digest=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',new Uint8Array(bytes).buffer))).map(b=>b.toString(16).padStart(2,'0')).join('');
 await env.BUCKET.put(RESULTS_KEY,bytes,{httpMetadata:{contentType:'application/json'},customMetadata:{sha256:digest,source_sha256:value.source_sha256}});return reply({saved:true,sha256:digest,bytes:bytes.length});
}
