import test from 'node:test';
import assert from 'node:assert/strict';
import {registerHooks} from 'node:module';
import {existsSync} from 'node:fs';
registerHooks({resolve(specifier,context,next){if(specifier.startsWith('.')&&!/\.[a-z]+$/.test(specifier)&&context.parentURL){const url=new URL(specifier+'.ts',context.parentURL);if(existsSync(url))return next(url.href,context);}return next(specifier,context);}});
const {validateExtraction,addSuggestions,EXTRACTION_MODEL}=await import('../lib/cv-extraction.ts');
const {emptyData,validateData}=await import('../lib/identity.ts');

test('uses the existing model, accepts paraphrases and adapts new categories',()=>{
 const result=validateExtraction({model:EXTRACTION_MODEL,suggestions:[{field:'skills',text:'Spatial analysis',quote:'A paraphrase is allowed'},{field:'unusual_expertise',text:'An uncommon field',quote:''}]});
 assert.equal(result.suggestions[1].field,'cv_notes');assert.equal(result.suggestions[1].text,'unusual_expertise: An uncommon field');
 assert.throws(()=>validateExtraction({...result,model:'qwen'}));
 assert.deepEqual(validateExtraction({model:EXTRACTION_MODEL,suggestions:[]}).suggestions,[]);
});

test('preserves typed answers, avoids duplicate additions and keeps long suggestions reviewable',()=>{
 const original=emptyData();original.identity.skills='Existing skill';
 const result={model:EXTRACTION_MODEL,suggestions:[{field:'skills',text:'New skill',quote:''}]};
 const merged=addSuggestions(original,result);
 assert.equal(original.identity.skills,'Existing skill');assert.equal(merged.data.identity.skills,'Existing skill\nNew skill');
 assert.equal(addSuggestions(merged.data,result).added,0);
 const oversized={model:EXTRACTION_MODEL,suggestions:[{field:'skills',text:'x'.repeat(100000),quote:''}]};
 assert.equal(addSuggestions(original,oversized).overflow,1);assert.equal(oversized.suggestions[0].text.length,100000);
});

test('own-note GPT consent is explicit, keeps opt-outs and does not opt in legacy exports',()=>{
 const fresh=emptyData();assert.equal(validateData(fresh).memory.network_context,true);
 fresh.memory.network_context=false;assert.equal(validateData(fresh).memory.network_context,false);
 delete fresh.memory.network_context;assert.equal(validateData(fresh).memory.network_context,false);
 fresh.memory.network_context='yes';assert.throws(()=>validateData(fresh));
});
