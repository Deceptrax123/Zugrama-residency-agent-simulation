"""Editable onboarding document with a deterministic, model-free round trip."""
import re

from .identity import FIELDS, QUESTIONS, validate_identity
from .identity_extract import validate_suggestions
from .store import AppError

PILLARS = (
    ('Name', ('name','nickname')), ('Given identity', ('nationality', 'region')),
    ('Skill identity', ('cv', 'skills','subject_expertise','products_built','source_website','interests','cv_notes')),
    ('Contribution and reciprocity', ('personal_offer', 'personal_seeking', 'skills_offer_people',
        'skills_need_people', 'environment_offer', 'environment_need', 'reciprocity')),
    ('Moral compass', tuple(QUESTIONS)), ('Public introduction', ('introduction',)),
)


def fenced(value):
    longest=max((len(match) for match in re.findall(r'`+', value)), default=0)
    fence='`'*max(3,longest+1)
    return [fence+'text',value,fence,'']


def document(value):
    lines=['# Identity','']
    for title,keys in PILLARS:
        lines+=['## '+title,'']
        for key in keys:
            lines+=['### '+FIELDS[key][0],'',*fenced(value.get(key,''))]
    lines+=['## Disclosure','',*fenced('yes' if value.get('share_values') else 'no')]
    return '\n'.join(lines)


def parse(raw):
    if not isinstance(raw,str) or not raw.strip() or len(raw)>100000:
        raise AppError('Provide an IDENTITY.md document of at most 100,000 characters')
    lines=raw.replace('\r\n','\n').split('\n');position=0
    def skip():
        nonlocal position
        while position<len(lines) and not lines[position].strip():position+=1
    def expect(expected):
        nonlocal position
        skip()
        if position>=len(lines) or lines[position]!=expected:
            raise AppError('Keep the IDENTITY.md headings and text fences. Expected: '+expected)
        position+=1
    def body():
        nonlocal position
        skip()
        match=re.fullmatch(r'(`{3,})text',lines[position]) if position<len(lines) else None
        if not match:raise AppError('Keep the opening text fence beneath each IDENTITY.md heading')
        fence=match.group(1);position+=1;start=position
        while position<len(lines) and lines[position]!=fence:position+=1
        if position==len(lines):raise AppError('A text fence in IDENTITY.md is not closed')
        value='\n'.join(lines[start:position]);position+=1
        return value
    expect('# Identity');value={}
    for title,keys in PILLARS:
        expect('## '+title)
        for key in keys:
            skip()
            old_labels={'cv':'### CV and experience','cv_notes':'### Other CV context'}
            if key in old_labels and position<len(lines) and lines[position]==old_labels[key]:
                position+=1;value[key]=body();continue
            if key in ('nickname','cv_notes','subject_expertise','products_built','source_website'):
                skip()
                if position>=len(lines) or lines[position]!='### '+FIELDS[key][0]:
                    value[key]='';continue  # Previously generated review documents stay editable.
            expect('### '+FIELDS[key][0]);value[key]=body()
    expect('## Disclosure');share=body().strip()
    if share not in ('yes','no'):raise AppError('Disclosure must be yes or no')
    value['share_values']=share=='yes';skip()
    if position!=len(lines):raise AppError('Put edits inside the existing IDENTITY.md text fences')
    return value


def review(payload):
    if set(payload)=={'identity'}:
        value=validate_identity(payload['identity'])
        return {'identity':value,'markdown':document(value)}
    if set(payload)!={'markdown','cv_evidence'}:
        raise AppError('Provide an identity draft or its edited IDENTITY.md and CV evidence')
    value=parse(payload['markdown'])
    notes=validate_suggestions({'suggestions':payload['cv_evidence']},value['cv'])
    value['cv_evidence']=[item for item in notes if item['text'] in value[item['field']]]
    value=validate_identity(value)
    # Canonicalise whitespace to match exactly the values saved and supplied to agents.
    return {'identity':value,'markdown':document(value)}
