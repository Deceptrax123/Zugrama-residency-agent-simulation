import {identitySchema} from './identity-fields';
export type Identity=Record<string,string|boolean>;
export type IntakeData={identity:Identity,budget:{limit_usd:string,reserve_usd:string},memory:{instructions:string,exclude_terms:string[],recall_enabled:boolean,capture_conversations:boolean,network_context?:boolean}};
export const emptyData=():IntakeData=>({identity:Object.fromEntries([...identitySchema.fields.map(f=>[f.key,'']),['share_values',false]]),budget:{limit_usd:'10.00',reserve_usd:'1.90'},memory:{instructions:"Prioritize people's interests and skills, ideas, commitments, stated priorities, and disagreements.",exclude_terms:[],recall_enabled:true,capture_conversations:true,network_context:true}});
function fence(text:string){const longest=Math.max(2,...Array.from(text.matchAll(/`+/g),m=>m[0].length));const f='`'.repeat(longest+1);return `${f}text\n${text}\n${f}\n`;}
export function identityMarkdown(identity:Identity){let result='# Identity\n\n';for(const [title,keys] of identitySchema.pillars){result+=`## ${title}\n\n`;for(const key of keys){const f=identitySchema.fields.find(f=>f.key===key)!;result+=`### ${f.label}\n\n${fence(String(identity[key]||''))}\n`;}}return result+'## Disclosure\n\n'+fence(identity.share_values?'yes':'no');}
export function parseIdentityMarkdown(raw:string):Identity{
 if(typeof raw!=='string'||raw.length>100000)throw Error('Keep IDENTITY.md below 100,000 characters.');const lines=raw.replaceAll('\r\n','\n').split('\n');let position=0;
 const skip=()=>{while(position<lines.length&&!lines[position].trim())position++;};const expect=(line:string)=>{skip();if(lines[position++]!==line)throw Error(`Keep the document headings. Expected: ${line}`);};
 const body=()=>{skip();const match=/^(`{3,})text$/.exec(lines[position++]||'');if(!match)throw Error('Keep the text fences below each heading.');const start=position;while(position<lines.length&&lines[position]!==match[1])position++;if(position===lines.length)throw Error('Close each text fence.');const text=lines.slice(start,position).join('\n').trim();position++;return text;};
 expect('# Identity');const value:Identity={};for(const [title,keys] of identitySchema.pillars){expect('## '+title);for(const key of keys){const field=identitySchema.fields.find(f=>f.key===key)!;skip();if(key==='nickname'&&lines[position]!=='### '+field.label){value[key]='';continue;}expect('### '+field.label);value[key]=body();}}expect('## Disclosure');const share=body();if(!['yes','no'].includes(share))throw Error('Disclosure should be yes or no.');value.share_values=share==='yes';skip();if(position!==lines.length)throw Error('Keep edits inside the existing text fences.');return value;
}
export function validateData(input:unknown,complete=false):IntakeData{
 const data=input as IntakeData;if(!data||typeof data!=='object'||!data.identity||!data.budget)throw Error('Provide your identity and allowance.');const identity:Identity={};
 for(const field of identitySchema.fields){const value=data.identity[field.key]??'';if(typeof value!=='string'||value.length>field.maximum||value.includes('\0'))throw Error(`Check ${field.label}.`);identity[field.key]=value.trim();}if(typeof data.identity.share_values!=='boolean')throw Error('Choose whether to share moral and political answers.');identity.share_values=data.identity.share_values;if(complete&&(!identity.name||!identity.introduction))throw Error('Add your name and public introduction before final review.');
 const amount=(v:unknown)=>{if(typeof v!=='string'||!/^\d{1,5}(\.\d{1,2})?$/.test(v)||Number(v)>10000)throw Error('Use USD amounts from 0 to 10000 with up to two decimals.');return v;};const limit=amount(data.budget.limit_usd),reserve=amount(data.budget.reserve_usd);if(Number(reserve)>Number(limit))throw Error('Keep the wrap-up reserve within your allowance.');
 return {identity,budget:{limit_usd:limit,reserve_usd:reserve},memory:memoryPreferences(data.memory)};
}

// Optional preferences must not block an otherwise complete introduction. Missing
// legacy choices stay off; never infer consent from a truthy string or a default.
export function memoryPreferences(input:unknown):IntakeData['memory']{
 const memory=(input??{}) as Partial<IntakeData['memory']>;
 if(typeof memory!=='object'||Array.isArray(memory))throw Error('Memory preferences must be an object.');
 const instructions=memory.instructions??'';
 if(typeof instructions!=='string'||instructions.length>2000||instructions.includes('\0'))throw Error('Keep memory priorities within 2,000 characters.');
 const exclusions=memory.exclude_terms??[];
 if(!Array.isArray(exclusions)||exclusions.some(t=>typeof t!=='string'||t.includes('\0')))throw Error('Memory exclusions must contain text.');
 const exclude_terms=exclusions.map(t=>t.trim()).filter(Boolean);
 if(exclude_terms.reduce((size,t)=>size+t.length,0)>100000)throw Error('Keep memory exclusions within 100,000 characters.');
 for(const key of ['recall_enabled','capture_conversations','network_context'] as const){
  if(memory[key]!==undefined&&typeof memory[key]!=='boolean')throw Error('Choose the memory options using the checkboxes.');
 }
 return {instructions,exclude_terms,recall_enabled:memory.recall_enabled??false,capture_conversations:memory.capture_conversations??false,network_context:memory.network_context??false};
}
