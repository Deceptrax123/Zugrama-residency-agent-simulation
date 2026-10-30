import {env} from 'cloudflare:workers';
import {getDb} from '../db';
import {cvJobs,extractionService} from '../db/schema';
import {and,eq,desc,lt} from 'drizzle-orm';
import {reply} from './api';
import {EXTRACTION_MODEL} from './cv-extraction';

export async function workerAuthorization(request:Request){
 const secret=env.EXTRACTION_WORKER_TOKEN;
 const expected='Bearer '+secret,actual=request.headers.get('Authorization')||'';
 let difference=actual.length^expected.length;
 for(let i=0;i<expected.length;i++)difference|=(actual.charCodeAt(i)||0)^expected.charCodeAt(i);
 if(!secret||difference)throw reply({error:'Extractor authorization required.'},401);
}

export async function expireJobs(){
 const now=Date.now();
 await getDb().update(cvJobs).set({status:'failed',completedAt:now,error:'Extraction was interrupted. No automatic model retry was made; you can try again.'})
  .where(and(eq(cvJobs.status,'processing'),lt(cvJobs.claimedAt,now-600000)));
}

export async function currentExtraction(owner:string,cvKey:string|null){
 await expireJobs();
 const service=(await getDb().select().from(extractionService).where(eq(extractionService.id,'host')).limit(1))[0];
 const online=!!service&&service.model===EXTRACTION_MODEL&&service.lastSeen>Date.now()-120000;
 if(!cvKey)return {job:null,processor_online:online};
 const job=(await getDb().select().from(cvJobs).where(and(eq(cvJobs.ownerId,owner),eq(cvJobs.cvKey,cvKey))).orderBy(desc(cvJobs.createdAt)).limit(1))[0];
 return {job:job?{id:job.id,status:job.status,error:job.error,result:job.status==='completed'&&job.result?JSON.parse(job.result):null}:null,processor_online:online};
}
