import test from 'node:test';
import assert from 'node:assert/strict';
import {createSubmissionKey,validSubmissionKey,submissionOwner} from '../lib/submission-key.ts';

test('new drafts get independent 256-bit capabilities',()=>{
 const keys=Array.from({length:64},()=>createSubmissionKey());
 assert.equal(new Set(keys).size,64);
 assert.ok(keys.every(key=>validSubmissionKey(key)&&key.length===43));
});
test('names and public identifiers cannot select a private submission',async()=>{
 for(const invalid of ['',null,'River','guest@example.test','../profile','a'.repeat(42),'a'.repeat(44),'a'.repeat(42)+'!']){
  assert.equal(validSubmissionKey(invalid),false);
  await assert.rejects(submissionOwner(invalid));
 }
});
test('storage keys are hashes, separate from legacy account IDs',async()=>{
 const key=createSubmissionKey(),other=createSubmissionKey();
 const owner=await submissionOwner(key);
 assert.match(owner,/^anonymous:[a-f0-9]{64}$/);
 assert.equal(await submissionOwner(key),owner);
 assert.notEqual(await submissionOwner(other),owner);
 assert.ok(!owner.includes(key));
});
