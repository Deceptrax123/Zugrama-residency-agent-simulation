import test from 'node:test';
import assert from 'node:assert/strict';
import {registerHooks} from 'node:module';
import {existsSync} from 'node:fs';
registerHooks({resolve(specifier,context,next){if(specifier.startsWith('.')&&!/\.[a-z]+$/.test(specifier)&&context.parentURL){const url=new URL(specifier+'.ts',context.parentURL);if(existsSync(url))return next(url.href,context);}return next(specifier,context);}});
const {emptyData,validateData,memoryPreferences}=await import('../lib/identity.ts');
test('long and numerous exclusions submit intact instead of the generic memory error',()=>{
 const data=emptyData();data.identity.name='Resident';data.identity.introduction='Hello';
 data.memory.exclude_terms=['private detail '.repeat(50),...Array.from({length:30},(_,i)=>'private '+i),'  ','  keep this  '];
 const saved=validateData(data,true);
 assert.deepEqual(saved.memory.exclude_terms,[...data.memory.exclude_terms.slice(0,-2).map(t=>t.trim()),'keep this']);
 assert.equal(saved.memory.capture_conversations,true);assert.equal(saved.memory.network_context,true);
});
test('optional or legacy missing memory preferences do not block submission or silently enable processing',()=>{
 const data=emptyData();data.identity.name='Resident';data.identity.introduction='Hello';delete data.memory;
 assert.deepEqual(validateData(data,true).memory,{instructions:'',exclude_terms:[],capture_conversations:false,recall_enabled:false,network_context:false});
 assert.deepEqual(memoryPreferences({instructions:'My priorities',recall_enabled:false}),{instructions:'My priorities',exclude_terms:[],capture_conversations:false,recall_enabled:false,network_context:false});
 const optedOut=emptyData().memory;for(const key of ['capture_conversations','recall_enabled','network_context'])optedOut[key]=false;
 assert.deepEqual(memoryPreferences(optedOut),optedOut);
});
test('malformed consent and oversized inputs still fail with specific messages',()=>{
 assert.throws(()=>memoryPreferences({network_context:'true'}),/checkboxes/);
 assert.throws(()=>memoryPreferences({exclude_terms:[7]}),/contain text/);
 assert.throws(()=>memoryPreferences({exclude_terms:['a'.repeat(100001)]}),/100,000/);
 assert.throws(()=>memoryPreferences({instructions:'a'.repeat(2001)}),/priorities/);
});
