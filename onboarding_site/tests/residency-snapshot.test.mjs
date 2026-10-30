import test from 'node:test';
import assert from 'node:assert/strict';
import {snapshotOwners} from '../lib/residency-snapshot.ts';
const residents=Array.from({length:50},(_,n)=>'anonymous:'+n.toString(16).padStart(64,'0'));
test('fifty residents plus host publish in batches without pruning other batches',()=>{
 const owners=[...residents,'host'];
 assert.deepEqual(snapshotOwners([{owner_id:residents[0]}],owners),owners);
 assert.deepEqual(snapshotOwners([{owner_id:'host'}],owners),owners);
 assert.equal(snapshotOwners(owners.map(owner_id=>({owner_id}))).length,51);
 assert.deepEqual(snapshotOwners([]),[]);
});
test('rejects over-capacity, duplicate, malformed or out-of-index owners',()=>{
 for(const owners of [[...residents,'anonymous:'+'f'.repeat(64)],[...residents,'host','host'],['host','bad']])assert.throws(()=>snapshotOwners([],owners));
 assert.throws(()=>snapshotOwners([{owner_id:residents[0]}],['host']));
 assert.throws(()=>snapshotOwners(Array(52).fill({owner_id:'host'})));
});
