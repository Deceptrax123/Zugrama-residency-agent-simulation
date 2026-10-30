import {env} from 'cloudflare:workers';
import {workerAuthorization} from '../../../../lib/extraction-service';
import {reply,failure,boundedBody} from '../../../../lib/api';
import {validateExtraction} from '../../../../lib/cv-extraction';

export async function POST(request:Request){try{
 await workerAuthorization(request);const payload=JSON.parse(new TextDecoder().decode(await boundedBody(request,300000)));
 if(typeof payload.id!=='string'||typeof payload.lease_token!=='string'||!['completed','failed'].includes(payload.status))throw Error('Provide a leased extraction result.');
 const job=await env.DB!.prepare('SELECT j.status,j.cv_key,s.cv_key AS current_cv FROM cv_jobs j JOIN submissions s ON s.user_id=j.owner_id WHERE j.id=? AND j.lease_token=?').bind(payload.id,payload.lease_token).first<{status:string,cv_key:string,current_cv:string}>();
 if(!job)return reply({error:'This extraction is no longer available.'},404);
 if(job.status==='completed')return reply({saved:true});
 if(job.status!=='processing'||job.cv_key!==job.current_cv)return reply({error:'The CV was replaced or the extraction was cancelled.'},409);
 const result=payload.status==='completed'?JSON.stringify(validateExtraction(payload.result)):null;
 const error=payload.status==='failed'?(typeof payload.error==='string'?payload.error.slice(0,1000):'CV extraction failed; no automatic retry was made.'):null;
 await env.DB!.prepare("UPDATE cv_jobs SET status=?,result=?,error=?,completed_at=? WHERE id=? AND lease_token=? AND status='processing'").bind(payload.status,result,error,Date.now(),payload.id,payload.lease_token).run();
 return reply({saved:true});
}catch(error){return failure(error);}}
