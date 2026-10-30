"""Private, event-scoped Markdown documents with machine-readable note blocks."""
import json
import os
import re
import tempfile


def write_private(path, text):
    path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    fd,temporary=tempfile.mkstemp(dir=path.parent,prefix='.memory-',suffix='.tmp')
    try:
        with os.fdopen(fd,'w',encoding='utf-8') as handle:
            handle.write(text);handle.flush();os.fsync(handle.fileno())
        os.replace(temporary,path)
        path.chmod(0o600)
    finally:
        if os.path.exists(temporary):os.unlink(temporary)


def document(notes):
    parts=['# Personal conversation memory\n\nPrivate to this agent and its human. Notes are model interpretations; sources retain who witnessed what.\n']
    for number,note in enumerate(notes,1):
        parts.append(f'\n## Note {number}\n\n'+note['memory']+'\n\n<details><summary>Provenance and retrieval data</summary>\n\n<!-- residency-note -->\n```json\n'+json.dumps(note,ensure_ascii=False)+'\n```\n\n</details>\n')
    return ''.join(parts)


def read_notes(path):
    if not path.exists():return []
    text=path.read_text(encoding='utf-8')
    return [json.loads(match.group(1)) for match in re.finditer(r'(?m)^<!-- residency-note -->\n```json\n([^\n]+)\n```$',text)]


def reflection_document(day,body):
    parts=[f'# Before sleep · day {day}\n\n{body["summary"]}\n']
    for key in ('takeaways','view_changes','unresolved_questions','tomorrow_intentions'):
        parts.append('\n## '+key.replace('_',' ').title()+'\n')
        parts.extend('\n- '+item['text']+'\n  Sources: '+', '.join(item['source_ids'])+'\n' for item in body[key])
    parts.append('\n<!-- residency-reflection -->\n```json\n'+json.dumps(body,ensure_ascii=False)+'\n```\n')
    return ''.join(parts)


def read_reflection(path):
    match=re.search(r'(?m)^<!-- residency-reflection -->\n```json\n([^\n]+)\n```$',path.read_text(encoding='utf-8'))
    return json.loads(match.group(1)) if match else None
