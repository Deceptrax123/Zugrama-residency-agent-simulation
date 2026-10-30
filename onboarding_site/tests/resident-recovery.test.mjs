import test from 'node:test';
import assert from 'node:assert/strict';
import {createRecoveryCode,normalizeRecoveryCode,recoveryDigest,RECOVERY_LIFETIME_MS} from '../lib/resident-recovery.ts';
test('recovery codes use 128 random bits and accept copied whitespace, grouping and case',async()=>{
 const codes=Array.from({length:128},()=>createRecoveryCode());
 assert.equal(new Set(codes).size,codes.length);assert.equal(RECOVERY_LIFETIME_MS,30*60*1000);
 for(const code of codes){assert.match(code,/^[A-F0-9]{8}(?:-[A-F0-9]{8}){3}$/);assert.equal(normalizeRecoveryCode(code),code.replaceAll('-','').toLowerCase());}
 const code=codes[0],hash=await recoveryDigest(code);
 assert.match(hash,/^[a-f0-9]{64}$/);assert.equal(await recoveryDigest('  '+code.toLowerCase().replaceAll('-',' ')+'\n'),hash);
 assert.notEqual(hash,await recoveryDigest(codes[1]));assert.ok(!hash.includes(normalizeRecoveryCode(code)));
});
test('names, identity IDs, short codes and malformed input cannot act as recovery codes',async()=>{
 for(const value of [null,{},4,'','Resident','123456','a'.repeat(31),'a'.repeat(33),'z'.repeat(32),'a'.repeat(101)]){
  assert.equal(normalizeRecoveryCode(value),null);await assert.rejects(recoveryDigest(value),/invalid, expired or already used/);
 }
});
