import {env} from 'cloudflare:workers';
import {bearer} from '../../../../lib/residency-access';
import {boundedBody,reply,failure} from '../../../../lib/api';
import {WATCH_CONFIG_KEY,watchDigest} from '../../../../lib/watch';
import {ensureWatchDb} from '../../../../lib/watch-db';
export async function POST(request:Request){try{
 if(!bearer(request,env.RESIDENCY_HOST_TOKEN))return reply({error:'Host access required.'},401);
 if(request.headers.get('origin')!==new URL(request.url).origin)return reply({error:'Use this site origin.'},403);
 const raw=JSON.parse(new TextDecoder().decode(await boundedBody(request,2000)));const digest=await watchDigest(raw.code);
 if(!digest||typeof raw.enabled!=='boolean')throw Error('Provide a shared code and enabled flag.');
 if(!env.BUCKET||!env.DB)return reply({error:'Watch storage unavailable.'},503);
 await ensureWatchDb(env.DB);const configured_at=Date.now();await env.BUCKET.put(WATCH_CONFIG_KEY,JSON.stringify({digest,enabled:raw.enabled,configured_at}),{httpMetadata:{contentType:'application/json'}});
 return reply({saved:true,enabled:raw.enabled,configured_at});
}catch(e){return failure(e);}}
