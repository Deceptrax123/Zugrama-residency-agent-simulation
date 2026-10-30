import test from 'node:test';
import assert from 'node:assert/strict';
import {registerHooks} from 'node:module';
import {existsSync} from 'node:fs';
registerHooks({resolve(specifier,context,next){if(specifier.startsWith('.')&&!/\.[a-z]+$/.test(specifier)&&context.parentURL){const url=new URL(specifier+'.ts',context.parentURL);if(existsSync(url))return next(url.href,context);}return next(specifier,context);}});
const {emptyData,identityMarkdown,parseIdentityMarkdown}=await import('../lib/identity.ts');
const {patchContributions}=await import('../lib/profile-contributions.ts');
function profile(){const data=emptyData();data.identity.name='Resident';data.identity.introduction='Hello';data.identity.moral_compass='Private values';delete data.memory.network_context;return data;}
test('changes only requested contribution fields in both representations, preserving legacy consent and private answers',()=>{
 const data=profile();const patch={skills_offer_people:' ML research ',skills_need_people:'Field knowledge',environment_offer:'Prototypes'};
 const result=patchContributions(JSON.stringify(data),identityMarkdown(data.identity),'reviewed',patch);
 const saved=JSON.parse(result.data);const expected=structuredClone(data);Object.assign(expected.identity,{...patch,skills_offer_people:'ML research'});
 assert.deepEqual(saved,expected);assert.deepEqual(parseIdentityMarkdown(result.markdown),expected.identity);
 assert.equal(Object.hasOwn(saved.memory,'network_context'),false);
});
test('rejects unrelated fields, malformed values and mismatched reviewed documents',()=>{
 const data=profile(),raw=JSON.stringify(data),md=identityMarkdown(data.identity);
 for(const patch of [{name:'Someone else'},{budget:{}},{skills_offer_people:7},{environment_offer:'a'.repeat(2001)},{},[]])assert.throws(()=>patchContributions(raw,md,'reviewed',patch));
 assert.throws(()=>patchContributions(raw,md.replace('Private values','Different values'),'reviewed',{environment_offer:'New'}));
});
test('updates the introduction and reviewed Markdown without altering private values, allowances or consent',()=>{
 const data=profile(),raw=JSON.stringify(data),md=identityMarkdown(data.identity);
 const result=patchContributions(raw,md,'reviewed',{introduction:' I work on geometric ML and agent memory. '});
 const saved=JSON.parse(result.data),expected=structuredClone(data);expected.identity.introduction='I work on geometric ML and agent memory.';
 assert.deepEqual(saved,expected);assert.deepEqual(parseIdentityMarkdown(result.markdown),expected.identity);
 assert.throws(()=>patchContributions(raw,md,'reviewed',{introduction:' '}));
 assert.throws(()=>patchContributions(raw,md,'reviewed',{introduction:'x'.repeat(2001)}));
});
test('replaces personal and village placeholders while preserving unrelated answers and consent',()=>{
 const data=profile();Object.assign(data.identity,{personal_seeking:'qwsqws',environment_need:'sqswq',reciprocity:'sqwsqws'});
 const patch={personal_offer:'Research discussion and coding',personal_seeking:'Research collaborators',environment_need:'Domain knowledge and feedback',reciprocity:'Reciprocal learning',skills:'Graph ML and agent memory',cv:'Relevant project context',source_website:'https://example.test'};
 const result=patchContributions(JSON.stringify(data),identityMarkdown(data.identity),'reviewed',patch),saved=JSON.parse(result.data),expected=structuredClone(data);Object.assign(expected.identity,patch);
 assert.deepEqual(saved,expected);assert.deepEqual(parseIdentityMarkdown(result.markdown),expected.identity);
 for(const key of ['moral_compass','political_standing','name','share_values','budget','memory'])assert.throws(()=>patchContributions(JSON.stringify(data),identityMarkdown(data.identity),'reviewed',{[key]:'Override'}));
});
test('uses each field limit and leaves a saved draft unreviewed',()=>{
 const data=profile(),context='c'.repeat(3000);
 const result=patchContributions(JSON.stringify(data),'','draft',{cv:context,personal_offer:'Technical support'});
 assert.equal(JSON.parse(result.data).identity.cv,context);assert.equal(result.markdown,'');
 assert.throws(()=>patchContributions(JSON.stringify(data),'','draft',{cv:'x'.repeat(16001)}));
 assert.throws(()=>patchContributions(JSON.stringify(data),'','draft',{personal_seeking:'x'.repeat(2001)}));
});
