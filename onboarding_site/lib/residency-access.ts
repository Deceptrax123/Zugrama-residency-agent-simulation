import {env} from 'cloudflare:workers';
import {authorize,record,reply} from './api';
export function bearer(request:Request,secret:string|undefined){
 const expected='Bearer '+secret,actual=request.headers.get('Authorization')||'';
 let difference=actual.length^expected.length;
 for(let n=0;n<expected.length;n++)difference|=(actual.charCodeAt(n)||0)^expected.charCodeAt(n);
 return !!secret&&!difference;
}
export function bridgeAccess(request:Request){if(!bearer(request,env.RESIDENCY_BRIDGE_TOKEN))throw reply({error:'Bridge authorization required.'},401);}
export async function residencyActor(request:Request,write=false){
 if(write&&request.headers.get('Origin')!==new URL(request.url).origin)throw reply({error:'Use this site to send requests.'},403);
 if(bearer(request,env.RESIDENCY_HOST_TOKEN))return 'host';
 const user=await authorize(request,write);const profile=await record(user.userId);
 if(!profile)throw reply({error:'Save your onboarding profile first.'},403);
 if(profile.status!=='reviewed'){
  const snapshot=await env.DB!.prepare('SELECT data FROM residency_snapshots WHERE owner_id=?').bind(user.userId).first<{data:string}>();
  const enrollment=snapshot?JSON.parse(snapshot.data)?.enrollment:null;
  if(enrollment?.basis!=='host_reviewed_draft'||enrollment?.source_status!=='draft')throw reply({error:'Review your introduction or wait for the organiser to enroll your saved profile.'},403);
 }
 return user.userId;
}
