"""Review-only import of a resident's independently saved onboarding bundle."""
from .store import AppError,text
from .budgets import dollars
from .identity_document import review


def memory_preferences(value):
    if not isinstance(value,dict) or not {'instructions','exclude_terms','recall_enabled','capture_conversations'}<=set(value) or set(value)-{'instructions','exclude_terms','recall_enabled','capture_conversations','network_context'}:
        raise AppError('Provide memory priorities, exclusions and recall/capture choices')
    result={'instructions':text(value['instructions'],'Memory priorities',2000,False)}
    phrases=value['exclude_terms']
    if not isinstance(phrases,list):raise AppError('Memory exclusions must be a list of text')
    result['exclude_terms']=[clean for phrase in phrases if (clean:=text(phrase,'Excluded phrase',100000,False))]
    if sum(map(len,result['exclude_terms']))>100000:raise AppError('Keep memory exclusions within 100,000 characters')
    for key in ('recall_enabled','capture_conversations'):
        if type(value[key]) is not bool:raise AppError('Memory preferences must be true or false')
        result[key]=value[key]
    if 'network_context' in value:
        if type(value['network_context']) is not bool:raise AppError('Choose whether your own notes may enter GPT context')
        result['network_context']=value['network_context']
    return result


def prepare(payload):
    if not isinstance(payload,dict) or set(payload)!={'bundle'}:raise AppError('Import one onboarding file')
    bundle=payload['bundle']
    if not isinstance(bundle,dict) or bundle.get('schema')!='dhun-residency-onboarding/v1':
        raise AppError('Choose a Dhun residency onboarding export')
    draft=review({'markdown':bundle.get('markdown'),'cv_evidence':[]})
    budget=bundle.get('budget')
    if not isinstance(budget,dict) or set(budget)!={'limit_usd','reserve_usd'}:raise AppError('The export needs a USD allowance and reserve')
    if dollars(budget['reserve_usd'])>dollars(budget['limit_usd']):raise AppError('The reserve must fit inside the allowance')
    memory=memory_preferences(bundle.get('memory'))
    cv=bundle.get('cv_pdf')
    source=''
    if cv is not None:
        if not isinstance(cv,dict) or set(cv)!={'name','base64'}:raise AppError('The saved CV must be a PDF')
        from .cv_pdf import pdf_text
        source=pdf_text(cv['base64'])
    return {**draft,'budget':budget,'memory_policy':memory,'cv_text':source,'external_processing':False}
