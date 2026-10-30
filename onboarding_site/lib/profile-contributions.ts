import {identityMarkdown,parseIdentityMarkdown,validateData} from './identity';
import {identitySchema} from './identity-fields';

const fields=['skills_offer_people','skills_need_people','environment_offer','introduction',
 'personal_offer','personal_seeking','environment_need','reciprocity','skills','cv','source_website'];

// A narrow organiser operation: no arbitrary field, account or budget changes.
export function patchContributions(rawData:string,markdown:string,status:string,patch:unknown){
 if(!patch||typeof patch!=='object'||Array.isArray(patch))throw Error('Provide contribution fields.');
 const changes=patch as Record<string,unknown>;
 if(!Object.keys(changes).length||Object.keys(changes).some(key=>!fields.includes(key)))throw Error('Only skills, project context, portfolio, contribution and public introduction fields can be updated.');
 for(const [key,value] of Object.entries(changes)){
  const maximum=identitySchema.fields.find(field=>field.key===key)!.maximum;
  if(typeof value!=='string'||value.length>maximum||value.includes('\0'))throw Error(`Keep ${key} within its ${maximum}-character field limit.`);
 }
 const original=JSON.parse(rawData);validateData(original,status==='reviewed');
 if(status==='reviewed'){
  const reviewed=parseIdentityMarkdown(markdown);
  for(const [key,value] of Object.entries(reviewed))if(value!==original.identity[key])throw Error('The reviewed document and saved fields differ. Review this profile before updating.');
 }
 const data={...original,identity:{...original.identity,...Object.fromEntries(Object.entries(changes).map(([key,value])=>[key,(value as string).trim()]))}};
 validateData(data,status==='reviewed');
 return {data:JSON.stringify(data),markdown:status==='reviewed'?identityMarkdown(data.identity):markdown};
}
