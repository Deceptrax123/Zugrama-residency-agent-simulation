import test from 'node:test';
import assert from 'node:assert/strict';
import {commandPayload} from '../lib/residency-command.ts';
const id='synthetic-request-1234',directory=[{id:'self'},{id:'peer'}];
test('resident requests can only be addressed to their own agent with an optional valid peer',()=>{
 assert.deepEqual(commandPayload('resident',{kind:'request',request_id:id,body:' Explore this idea ',target_id:'peer'},directory,'self'),{kind:'request',payload:{body:'Explore this idea',target_id:'peer'}});
 assert.equal(commandPayload('resident',{kind:'request',request_id:id,body:'Open question'},directory,'self').payload.target_id,null);
 for(const extra of [{kind:'start'},{owner_id:'someone-else'},{target_id:'self'},{target_id:'unknown'},{body:''},{body:'x'.repeat(4001)}])assert.throws(()=>commandPayload('resident',{kind:'request',request_id:id,body:'A request',...extra},directory,'self'));
});
test('host Start requires explicit confirmation and bounded settings',()=>{
 const payload={kind:'start',request_id:id,max_calls:14,npc_enabled:true,seven_days:true,confirmed:true};
 assert.equal(commandPayload('host',payload,[]).kind,'start');
 for(const extra of [{confirmed:false},{max_calls:0},{max_calls:61},{max_calls:2.5},{npc_enabled:'yes'},{seven_days:undefined}])assert.throws(()=>commandPayload('host',{...payload,...extra},[]));
 assert.throws(()=>commandPayload('host',{kind:'request',request_id:id,body:'Anything'},[]));
});
test('live host Start has no call cap by default and preserves explicit null across the bridge',()=>{
 const payload={kind:'start',request_id:id,npc_enabled:true,seven_days:true,confirmed:true};
 assert.equal(commandPayload('host',payload,[]).payload.max_calls,null);
 assert.equal(commandPayload('host',{...payload,max_calls:null},[]).payload.max_calls,null);
});
