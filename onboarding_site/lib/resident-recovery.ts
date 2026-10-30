// Recovery codes contain 128 random bits. Only a domain-separated hash is stored.
export const RECOVERY_LIFETIME_MS=30*60*1000;
export function createRecoveryCode(){
 const hex=Array.from(crypto.getRandomValues(new Uint8Array(16)),n=>n.toString(16).padStart(2,'0')).join('');
 return hex.match(/.{8}/g)!.join('-').toUpperCase();
}
export function normalizeRecoveryCode(value:unknown){
 if(typeof value!=='string'||value.length>100)return null;
 const code=value.replace(/[\s-]/g,'').toLowerCase();
 return /^[a-f0-9]{32}$/.test(code)?code:null;
}
export async function recoveryDigest(value:unknown){
 const normalized=normalizeRecoveryCode(value);
 if(!normalized)throw Error('This recovery code is invalid, expired or already used. Ask the host for a new code.');
 const bytes=await crypto.subtle.digest('SHA-256',new TextEncoder().encode('zugrama recovery/v1:'+normalized));
 return Array.from(new Uint8Array(bytes),n=>n.toString(16).padStart(2,'0')).join('');
}
