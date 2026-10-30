import {identitySchema} from './identity-fields';
import type {IntakeData} from './identity';

export const EXTRACTION_MODEL='gpt-5.6-terra';
export const CV_TARGETS=['cv','skills','subject_expertise','products_built','interests','personal_offer','personal_seeking','skills_offer_people','skills_need_people','environment_offer','environment_need','reciprocity','cv_notes'];
export type Suggestion={field:string,text:string,quote:string};
export type ExtractionResult={model:string,suggestions:Suggestion[]};
export type ExtractionJob={id:string,status:string,error:string|null,result:ExtractionResult|null};
export type ExtractionState={job:ExtractionJob|null,processor_online:boolean};

export function validateExtraction(input:unknown):ExtractionResult {
 const result=input as ExtractionResult;
 if(!result||result.model!==EXTRACTION_MODEL||!Array.isArray(result.suggestions))throw Error('The extractor must use the configured GPT Terra model.');
 const suggestions:Suggestion[]=[];
 for(const item of result.suggestions){
  if(!item||typeof item.field!=='string'||typeof item.text!=='string'||typeof item.quote!=='string')throw Error('Invalid extraction response.');
  if(!item.text.trim())continue;
  const known=CV_TARGETS.includes(item.field);
  suggestions.push({field:known?item.field:'cv_notes',text:known?item.text:item.field+': '+item.text,quote:item.quote});
 }
 return {model:EXTRACTION_MODEL,suggestions};
}

export function addSuggestions(data:IntakeData,result:ExtractionResult){
 const identity={...data.identity};let added=0,overflow=0;
 for(const note of result.suggestions){
  const maximum=identitySchema.fields.find(field=>field.key===note.field)?.maximum;
  if(!maximum)continue;
  const existing=String(identity[note.field]||'');
  if(existing.includes(note.text))continue;
  const combined=[existing,note.text].filter(Boolean).join('\n');
  if(combined.length>maximum){overflow++;continue;}
  identity[note.field]=combined;added++;
 }
 return {data:{...data,identity},added,overflow};
}
