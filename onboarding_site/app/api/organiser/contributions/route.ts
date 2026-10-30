import {env} from 'cloudflare:workers';
import {reply,failure,boundedBody} from '../../../../lib/api';
import {patchContributions} from '../../../../lib/profile-contributions';

export async function POST(request:Request){try{
 const secret=env.PROFILE_ADMIN_TOKEN,expected='Bearer '+secret,actual=request.headers.get('Authorization')||'';
 let difference=actual.length^expected.length;
 for(let i=0;i<expected.length;i++)difference|=(actual.charCodeAt(i)||0)^expected.charCodeAt(i);
 if(!secret||difference)return reply({error:'Organiser authorization required.'},401);
 const payload=JSON.parse(new TextDecoder().decode(await boundedBody(request,16000)));
 if(typeof payload.user_id!=='string'||!payload.user_id||payload.user_id.length>200)return reply({error:'Provide an exact submission ID.'},400);
 const row=await env.DB!.prepare('SELECT * FROM submissions WHERE user_id=?').bind(payload.user_id).first<{user_id:string,data:string,markdown:string,status:string,updated_at:string}>();
 if(!row)return reply({error:'Submission not found.'},404);
 if(payload.action==='read')return reply({submission:row});
 if(payload.action!=='patch'||payload.confirmed!==true)return reply({error:'Confirm a contribution update.'},400);
 if(typeof payload.expected_updated_at!=='string'||payload.expected_updated_at!==row.updated_at)return reply({error:'The profile changed. Read it again before updating.'},409);
 const result=patchContributions(row.data,row.markdown,row.status,payload.patch);
 const now=new Date().toISOString();
 const saved=await env.DB!.prepare('UPDATE submissions SET data=?,markdown=?,updated_at=? WHERE user_id=? AND updated_at=? AND data=? AND markdown=? AND status=?')
  .bind(result.data,result.markdown,now,row.user_id,row.updated_at,row.data,row.markdown,row.status).run();
 if(saved.meta.changes!==1)return reply({error:'The profile changed. No update was made.'},409);
 return reply({saved:true,user_id:row.user_id,updated_at:now,fields:Object.keys(payload.patch)});
}catch(error){return failure(error);}}
