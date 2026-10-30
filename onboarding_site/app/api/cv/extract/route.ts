import {env} from 'cloudflare:workers';
import {authorize,record,reply,failure,boundedBody} from '../../../../lib/api';
import {currentExtraction} from '../../../../lib/extraction-service';

export async function GET(request:Request){try{
 const user=await authorize(request);const saved=await record(user.userId);
 return reply(await currentExtraction(user.userId,saved?.cvKey||null));
}catch(error){return failure(error);}}

export async function POST(request:Request){try{
 const user=await authorize(request,true);
 if(!env.EXTRACTION_WORKER_TOKEN)return reply({error:'The CV extractor is not configured. Your PDF remains saved.'},503);
 const payload=JSON.parse(new TextDecoder().decode(await boundedBody(request,4096)));
 if(!payload||Object.keys(payload).some(key=>key!=='retry')||typeof payload.retry!=='boolean')throw Error('Choose whether to retry extraction.');
 const saved=await record(user.userId);if(!saved?.cvKey)throw Error('Upload a CV PDF first.');
 const state=await currentExtraction(user.userId,saved.cvKey);
 if(state.job&&(['queued','processing'].includes(state.job.status)||(!payload.retry&&state.job.status==='completed')))return reply(state);
 const db=env.DB!;
 const limits=await db.prepare('SELECT count(*) AS total,sum(CASE WHEN owner_id=? THEN 1 ELSE 0 END) AS own FROM cv_jobs WHERE created_at>?').bind(user.userId,Date.now()-86400000).first<{total:number,own:number}>();
 if((limits?.own||0)>=10||(limits?.total||0)>=100)return reply({error:'The daily CV extraction limit has been reached. Your PDF is saved; try again later.'},429);
 await db.prepare("INSERT INTO cv_jobs(id,owner_id,cv_key,status,created_at) SELECT ?,?,?,'queued',? WHERE NOT EXISTS(SELECT 1 FROM cv_jobs WHERE owner_id=? AND cv_key=? AND status IN ('queued','processing'))").bind(crypto.randomUUID(),user.userId,saved.cvKey,Date.now(),user.userId,saved.cvKey).run();
 return reply(await currentExtraction(user.userId,saved.cvKey));
}catch(error){return failure(error);}}
