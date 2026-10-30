import {getChatGPTUser} from '../app/chatgpt-auth';
import {getDb} from '../db';
import {submissions,residentAccessKeys} from '../db/schema';
import {eq} from 'drizzle-orm';
import {submissionOwner,validSubmissionKey} from './submission-key';
export async function authorize(request:Request,write=false){
 if(write&&request.headers.get('origin')!==new URL(request.url).origin)throw reply({error:'Use the form on this site.'},403);
 const key=request.headers.get('X-Submission-Key');
 if(key!==null){
  if(!validSubmissionKey(key))throw reply({error:'Your private return link is incomplete. Open the saved link again.'},401);
  const hash=await submissionOwner(key);
  const alias=(await getDb().select({ownerId:residentAccessKeys.ownerId}).from(residentAccessKeys).where(eq(residentAccessKeys.accessHash,hash)).limit(1))[0];
  return {userId:alias?.ownerId||hash};
 }
 // Preserve access to submissions saved before account-free onboarding. The
 // public form never invokes sign-in or needs these optional dispatch headers.
 const legacy=await getChatGPTUser();if(legacy)return {userId:legacy.userId};
 throw reply({error:'Open your personal return link, or start a new introduction on this site.'},401);
}
export async function record(userId:string){return (await getDb().select().from(submissions).where(eq(submissions.userId,userId)).limit(1))[0]||null;}
export function reply(value:unknown,status=200){return Response.json(value,{status,headers:{'Cache-Control':'no-store','X-Content-Type-Options':'nosniff','Referrer-Policy':'no-referrer'}});}
export function failure(error:unknown){if(error instanceof Response)return error;return reply({error:error instanceof Error?error.message:'Unable to save. Please try again.'},400);}
export async function boundedBody(request:Request,maximum:number){
 const reader=request.body?.getReader();if(!reader)return new Uint8Array();const chunks:Uint8Array[]=[];let size=0;
 try{for(;;){const {value,done}=await reader.read();if(done)break;size+=value.byteLength;if(size>maximum){await reader.cancel();throw new Response(JSON.stringify({error:'This upload is too large.'}),{status:413,headers:{'Content-Type':'application/json'}});}chunks.push(value);}}finally{reader.releaseLock();}
 const bytes=new Uint8Array(size);let position=0;for(const chunk of chunks){bytes.set(chunk,position);position+=chunk.byteLength;}return bytes;
}
