'use client';
import {useEffect,useState} from 'react';
import {createSubmissionKey} from '../lib/submission-key';

export async function recovery(body:unknown,hostKey?:string){
 const response=await fetch('/api/residency/recovery',{method:'POST',headers:{'Content-Type':'application/json',...(hostKey?{Authorization:'Bearer '+hostKey}:{})},body:JSON.stringify(body)});
 const value=await response.json() as {error?:string,restored?:boolean,code?:string,expires_at?:number};
 if(!response.ok)throw Error(value.error||'Unable to restore access. Please try again.');
 return value;
}
export async function redeemResidentCode(code:string){const key=createSubmissionKey();await recovery({action:'redeem',code,access_key:key});return key;}
export function ResidentRecovery({onRestore}:{onRestore:(key:string)=>void}){
 const [code,setCode]=useState(''),[busy,setBusy]=useState(false),[error,setError]=useState(''),[open,setOpen]=useState(false),[ready,setReady]=useState(false);
 useEffect(()=>{setReady(true);const supplied=new URLSearchParams(location.hash.slice(1)).get('recover');if(supplied){setCode(supplied);setOpen(true);history.replaceState(null,'',location.pathname);}},[]);
 const restore=async(event:React.FormEvent)=>{
  event.preventDefault();setBusy(true);setError('');
  try{const key=await redeemResidentCode(code);setCode('');onRestore(key);}catch(e){setError((e as Error).message);}finally{setBusy(false);}
 };
 return <section className="panel recovery-panel"><button type="button" className="text-button recovery-toggle" disabled={!ready} aria-expanded={open} aria-controls="recovery-form" onClick={()=>setOpen(!open)}>Lost your link? Recover access</button>{open&&<div id="recovery-form"><p>Ask the residency host for a recovery code for your agent. Enter it here to restore your profile and dashboard on this browser. No sign-in needed.</p><form onSubmit={restore}><label htmlFor="recovery-code">One-time recovery code</label><input id="recovery-code" autoComplete="off" autoCapitalize="characters" spellCheck={false} maxLength={100} required value={code} onChange={e=>setCode(e.target.value)} placeholder="Paste the code from your host"/><button className="primary" disabled={busy||!code.trim()}>{busy?'Restoring…':'Recover my agent'}</button></form>{error&&<p role="alert" className="error">{error}</p>}<p className="helper">Codes work once and expire after 30 minutes. Only the host can issue them.</p></div>}</section>;
}
export function HostResidentRecovery({memberId,name,hostKey}:{memberId:string,name:string,hostKey:string}){
 const [issued,setIssued]=useState<{code:string,expires_at:number}|null>(null),[busy,setBusy]=useState(false),[error,setError]=useState(''),[copied,setCopied]=useState(false);
 const issue=async()=>{setBusy(true);setError('');setCopied(false);try{const value=await recovery({action:'issue',member_id:memberId},hostKey);setIssued({code:value.code!,expires_at:value.expires_at!});}catch(e){setError((e as Error).message);}finally{setBusy(false);}};
 return <div className="host-recovery"><button type="button" className="secondary" disabled={busy} onClick={issue}>{busy?'Creating code…':issued?'Replace recovery code':'Create recovery code'}</button>{issued&&<div className="recovery-issued"><p>Confirm this is {name}, then share this code privately.</p><label htmlFor={'code-'+memberId}>Recovery code for {name}</label><input id={'code-'+memberId} readOnly value={issued.code} onFocus={e=>e.currentTarget.select()}/><p className="helper">Expires {new Date(issued.expires_at).toLocaleTimeString()}. Works once. Creating another code replaces this one.</p><button type="button" className="text-button" onClick={async()=>{try{await navigator.clipboard.writeText(issued.code);setCopied(true);}catch{setError('Select and copy the code above.');}}}>{copied?'Code copied':'Copy code'}</button><button type="button" className="text-button" onClick={()=>{setIssued(null);setCopied(false);}}>Hide code</button></div>}{error&&<p className="error" role="alert">{error}</p>}</div>;
}
