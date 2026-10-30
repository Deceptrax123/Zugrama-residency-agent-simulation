import {env} from 'cloudflare:workers';
import {getDb} from '../../../../db';
import {extractionService} from '../../../../db/schema';
import {workerAuthorization,expireJobs} from '../../../../lib/extraction-service';
import {reply,failure} from '../../../../lib/api';
import {EXTRACTION_MODEL} from '../../../../lib/cv-extraction';

export async function POST(request:Request){try{
 await workerAuthorization(request);await expireJobs();const now=Date.now();
 await getDb().insert(extractionService).values({id:'host',lastSeen:now,model:EXTRACTION_MODEL}).onConflictDoUpdate({target:extractionService.id,set:{lastSeen:now,model:EXTRACTION_MODEL}});
 const job=await env.DB!.prepare("UPDATE cv_jobs SET status='processing',claimed_at=?,lease_token=? WHERE id=(SELECT id FROM cv_jobs WHERE status='queued' ORDER BY created_at,id LIMIT 1) AND status='queued' RETURNING id,owner_id,cv_key,lease_token")
  .bind(now,crypto.randomUUID()).first<{id:string,owner_id:string,cv_key:string,lease_token:string}>();
 if(!job)return reply({job:null});
 const object=await env.BUCKET?.get(job.cv_key);
 if(!object){await env.DB!.prepare("UPDATE cv_jobs SET status='failed',error=?,completed_at=? WHERE id=?").bind('The PDF was replaced or removed. Upload it again to extract.',now,job.id).run();return reply({job:null});}
 const bytes=new Uint8Array(await object.arrayBuffer());let binary='';for(let i=0;i<bytes.length;i+=8192)binary+=String.fromCharCode(...bytes.subarray(i,i+8192));
 return reply({job:{id:job.id,lease_token:job.lease_token,pdf_base64:btoa(binary),model:EXTRACTION_MODEL}});
}catch(error){return failure(error);}}
