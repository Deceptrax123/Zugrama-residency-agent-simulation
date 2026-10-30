"""Audit native Hermes input coverage without exporting private input values."""
import json
from pathlib import Path

CAP = 65536

def compact(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'))

def native_text(payload):
    content = payload['messages'][-1]['content']
    if isinstance(content, str):
        return content[:CAP]
    return '\n'.join(part['text'][:CAP] for part in content if part.get('type') == 'text')

def value_exposure(text, value, visible):
    source = compact(value)
    start = text.find(source)
    if start < 0:
        raise ValueError('Coverage value is not present in the saved request')
    if start >= len(visible):
        return 'absent'
    return 'full' if start + len(source) <= len(visible) else 'partial'

def field_exposure(text, key, visible):
    """Locate a top-level JSON field independent of whitespace/ASCII encoding."""
    decoder=json.JSONDecoder();index=0
    while index<len(text) and text[index].isspace():index+=1
    if text[index]!='{':raise ValueError('Expected a JSON object')
    index+=1
    while index<len(text):
        while text[index].isspace() or text[index]==',':index+=1
        if text[index]=='}':break
        field,end=decoder.raw_decode(text,index);index=end
        while text[index].isspace():index+=1
        if text[index]!=':':raise ValueError('Missing JSON field separator')
        index+=1
        while text[index].isspace():index+=1
        start=index;_,index=decoder.raw_decode(text,index)
        if field==key:
            return 'absent' if start>=len(visible) else 'full' if index<=len(visible) else 'partial'
    raise ValueError('Missing coverage field')

def request_coverage(directory):
    directory = Path(directory)
    request = json.loads((directory / 'request.json').read_text())
    text = request['messages'][-1]['content']
    context = json.loads(text)
    wire_path = directory / 'wire-request.json'
    wire = json.loads(wire_path.read_text()) if wire_path.exists() else request
    visible = native_text(wire)
    safe = isinstance(wire['messages'][-1]['content'], list)
    counts = {'full': 0, 'partial': 0, 'absent': 0}
    for message in context.get('messages', []):
        counts['full' if safe else value_exposure(text, message, visible)] += 1
    result = {'input_characters': len(text), 'message_exposure': counts,
              'transport': 'structured text parts; JSON values preserved' if safe else 'single text part; native limit 65536 characters',
              'input_values_preserved': safe or len(text) <= CAP}
    if 'reference_guide' in context:
        result['reference_guide'] = 'full' if safe else value_exposure(text, context['reference_guide'], visible)
    return result

def check_answer_exposure(directory, answers):
    """Exact quote must occur within the native-visible part of its own source."""
    directory = Path(directory)
    request = json.loads((directory / 'request.json').read_text())
    text = request['messages'][-1]['content'];context = json.loads(text)
    wire_path = directory / 'wire-request.json'
    wire = json.loads(wire_path.read_text()) if wire_path.exists() else request
    safe = isinstance(wire['messages'][-1]['content'], list)
    visible = native_text(wire)
    aliases_path = directory / 'citation-aliases.json'
    if not aliases_path.exists() and directory.name.endswith('-correction'):
        aliases_path = directory.with_name(directory.name[:-len('-correction')]) / 'citation-aliases.json'
    aliases = json.loads(aliases_path.read_text()) if aliases_path.exists() else {}
    sources = {aliases.get(m['id'], m['id']): m for m in context['messages']}
    for answer in answers:
        for evidence in answer.get('evidence', []):
            source = sources[evidence['message_id']]
            if evidence['quote'] not in source['body']:
                raise ValueError('Quote is not in its supplied source')
            if not safe:
                raw = compact(source);start = text.find(raw)
                fragment = text[start:min(start + len(raw), len(visible))] if start >= 0 else ''
                if json.dumps(evidence['quote'], ensure_ascii=False)[1:-1] not in fragment:
                    raise ValueError('Answer cites a quote beyond native input coverage')
    return request_coverage(directory)
