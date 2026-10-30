import {authorize,record,reply,failure,boundedBody} from '../../../lib/api';
import {getDb} from '../../../db';
import {submissions} from '../../../db/schema';
import {eq} from 'drizzle-orm';
import {validateData,parseIdentityMarkdown,identityMarkdown} from '../../../lib/identity';
import {env} from 'cloudflare:workers';
export async function GET(request:Request){try{const user=await authorize(request);const row=await record(user.userId);return reply(row?{...JSON.parse(row.data),markdown:row.markdown,status:row.status,updated_at:row.updatedAt,cv:row.cvKey?{name:row.cvName,size:row.cvSize}:null}:null);}catch(error){return failure(error);}}
export async function POST(request:Request){try{
 const user=await authorize(request,true);if(!request.headers.get('content-type')?.startsWith('application/json'))return reply({error:'Send the form as JSON.'},415);const raw=new TextDecoder().decode(await boundedBody(request,900000));if(raw.length>230000)return reply({error:'The introduction is too long.'},413);const payload=JSON.parse(raw);if(!['draft','reviewed'].includes(payload.status))throw Error('Choose draft or reviewed.');const data=validateData(payload.data,payload.status==='reviewed');
 if(payload.status==='reviewed'){data.identity=parseIdentityMarkdown(payload.markdown);validateData(data,true);if(payload.consent!==true)throw Error('Confirm that you have reviewed your submission.');}
 const markdown=payload.status==='reviewed'?identityMarkdown(data.identity):'';const now=new Date().toISOString();await getDb().insert(submissions).values({userId:user.userId,data:JSON.stringify(data),markdown,status:payload.status,updatedAt:now}).onConflictDoUpdate({target:submissions.userId,set:{data:JSON.stringify(data),markdown,status:payload.status,updatedAt:now}});return reply({status:payload.status,markdown,updated_at:now});
 }catch(error){return failure(error);}}
export async function DELETE(request:Request){try{const user=await authorize(request,true);const row=await record(user.userId);await getDb().delete(submissions).where(eq(submissions.userId,user.userId));if(row?.cvKey)await env.BUCKET?.delete(row.cvKey);return reply({deleted:true});}catch(error){return failure(error);}}
