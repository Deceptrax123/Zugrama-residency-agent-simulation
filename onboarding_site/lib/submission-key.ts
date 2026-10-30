// An anonymous draft capability, never a name, email, or account identifier.
export const KEY_STORAGE='zugrama-private-draft-v1';
export const validSubmissionKey=(key:unknown):key is string=>typeof key==='string'&&/^[A-Za-z0-9_-]{43}$/.test(key);
export function createSubmissionKey(){const bytes=crypto.getRandomValues(new Uint8Array(32));return btoa(String.fromCharCode(...bytes)).replaceAll('+','-').replaceAll('/','_').replaceAll('=','');}
export async function submissionOwner(key:string){if(!validSubmissionKey(key))throw Error('Invalid private return link.');const digest=await crypto.subtle.digest('SHA-256',new TextEncoder().encode(key));return 'anonymous:'+Array.from(new Uint8Array(digest),n=>n.toString(16).padStart(2,'0')).join('');}
