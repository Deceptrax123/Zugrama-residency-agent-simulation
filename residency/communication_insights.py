"""Extractive, evidence-linked views of one agent's witnessed communication.

No inference calls, assigned topic taxonomy or hidden-room content. Topic labels
are frequent words/phrases, and named references never prove a relay occurred.
"""
from collections import Counter,defaultdict
import math
import re

STOP=set('''a an the and or but if then so because as at by for from in into of on onto to up with without about after before during through over under between this that these those it its is are was were be been being am i me my we us our you your he him his she her they them their who what when where why how which not no yes can could would should will may might must do does did done have has had having also just really very much some any all each other more most less than too now here there still already again let lets think thinking said says say told tell asking ask asked talking talk talked please thanks thank thankyou hello hi hey well okay ok perhaps maybe sure agree agreed sounds great good interesting something anything everything things thing want wants wanted like liked need needs needed know knows known see seen get got make made use used using instead together today tomorrow yesterday'''.split())
STOP.update('mention mentioned mentions explore explores exploring discuss discusses discussed discussing'.split())
WORD=re.compile(r"[^\W\d_]+(?:['’-][^\W\d_]+)?",re.UNICODE)


def aliases(directory):
    names=defaultdict(set)
    for person in directory:
        for name in (person['name'],person.get('nickname',''),person['name'].split()[0]):
            normalized=name.strip().casefold()
            if len(normalized)>=3:names[normalized].add(person['id'])
    return {name:next(iter(people)) for name,people in names.items() if len(people)==1}


def topics(messages,people):
    ignored={word.casefold() for p in people for name in (p['name'],p.get('nickname','')) for word in WORD.findall(name)}
    counts=Counter();documents=defaultdict(list)
    for message in messages[-200:]:
        candidates=set()
        for sentence in re.split(r'[.!?;:\n]+',message['body'][:1600]):
            words=[w.casefold() for w in WORD.findall(sentence)]
            for n in (1,2,3):
                for start in range(len(words)-n+1):
                    phrase=words[start:start+n]
                    if any(w in STOP or w in ignored or not 3<=len(w)<=32 for w in phrase):continue
                    term=' '.join(phrase);counts[term]+=1;candidates.add(term)
        for term in candidates:documents[term].append(message)
    def score(term):return counts[term]*(len(term.split())**1.2)*(1+.2*math.log1p(len(documents[term])))
    ranked=sorted(counts,key=lambda t:(-score(t),-len(t),t));selected=[];covered_words=set()
    for term in ranked:
        if len(term.split())>1 and len(documents[term])>=2:
            covered_words.update(word for word in term.split() if counts[term]*3>=counts[word])
    for term in ranked:
        if any(' '+term+' ' in ' '+old+' ' or ' '+old+' ' in ' '+term+' ' for old in selected):continue
        if len(term.split())==1 and term in covered_words:continue
        selected.append(term)
        if len(selected)==6:break
    def excerpt(message,term):
        match=re.search(r'(?<!\w)'+r'\W+'.join(re.escape(word) for word in term.split())+r'(?!\w)',message['body'],re.IGNORECASE)
        start=max(0,(match.start() if match else 0)-45)
        return message['body'][start:start+240]
    return [{'label':term,'message_count':len(documents[term]),'sources':[{'message_id':m['id'],'conversation_id':m['conversation_id'],'speaker_id':m['sender_id'],'excerpt':excerpt(m,term)} for m in documents[term][-2:]]} for term in selected]


def communication_insights(member,messages,visits,directory,end_at,semantic_only=False):
    people={p['id']:p for p in directory};names=aliases(directory)
    messages=sorted((m for m in messages if m['sender_id'] in people),key=lambda m:m['seq'])
    boundaries=defaultdict(list);room_members=defaultdict(set)
    for visit in visits:
        if visit['member_id'] in people:
            key=(visit['conversation_id'],visit['member_id']);boundaries[key].append((visit['joined_after_seq'],visit['left_after_seq']));room_members[visit['conversation_id']].add(visit['member_id'])
    def witnessed(person,message):return any(message['seq']>start and (finish is None or message['seq']<=finish) for start,finish in boundaries[(message['conversation_id'],person)])
    # Recheck the access boundary even though callers already pass scoped rows.
    visible=[m for m in messages if witnessed(member,m)]
    deliveries=[]
    for message in visible:
        if message['sender_id']==member:
            targets=sorted(p for p in room_members[message['conversation_id']] if p!=member and witnessed(p,message))
        else:targets=[member]
        deliveries.append((message,targets))
    windows=[];topic_cache={}
    for seconds in (0,60,300,900):
        selected=[(m,targets) for m,targets in deliveries if m['created_at']<=end_at and (not seconds or m['created_at']>end_at-seconds)]
        counters=Counter();contacts=defaultdict(lambda:{'sent':0,'received':0,'rooms':set(),'last_at':0})
        timeline=[];mentions=[]
        for message,targets in selected:
            sender=message['sender_id']
            for target in targets:
                counters[(sender,target)]+=1;peer=target if sender==member else sender
                contacts[peer]['sent' if sender==member else 'received']+=1;contacts[peer]['rooms'].add(message['conversation_id']);contacts[peer]['last_at']=max(contacts[peer]['last_at'],message['created_at'])
            evidence={'message_id':message['id'],'conversation_id':message['conversation_id'],'at':message['created_at'],'speaker_id':sender,'recipients':targets,'excerpt':message['body'][:300]}
            timeline.append(evidence)
            referenced=set()
            for name,person in names.items():
                if person in (sender,member) or person in targets or person in referenced:continue
                if re.search(r'(?<!\w)'+re.escape(name)+r'(?!\w)',message['body'],re.IGNORECASE):
                    referenced.add(person);mentions.append({**evidence,'referenced_id':person,'verification':'A name was mentioned; the original exchange is not verified.'})
        linked={member,*contacts}
        graph={'window_seconds':seconds,'nodes':[{'id':p,'name':people[p]['name'],'npc':people[p].get('npc',False)} for p in people if p in linked],
            'edges':[{'source':a,'target':b,'count':count} for (a,b),count in sorted(counters.items())]}
        connections=[{'id':p,'name':people[p]['name'],'sent':v['sent'],'received':v['received'],'room_count':len(v['rooms']),'last_at':v['last_at']} for p,v in sorted(contacts.items(),key=lambda item:(-item[1]['last_at'],item[0]))]
        if semantic_only:mentions=[]
        topic_messages=[m for m,_ in selected][-200:];cache_key=tuple(m['id'] for m in topic_messages)
        if cache_key not in topic_cache:topic_cache[cache_key]=[] if semantic_only else topics(topic_messages,directory)
        windows.append({'seconds':seconds,'graph':graph,'connections':connections,'topics':topic_cache[cache_key],'topic_messages_analyzed':len(topic_messages),'timeline':timeline[-15:][::-1],'mentions':mentions[-8:][::-1],
            'stats':{'sent':sum(m['sender_id']==member for m,_ in selected),'received':sum(m['sender_id']!=member for m,_ in selected),'connections':len(contacts),'rooms':len({m['conversation_id'] for m,_ in selected})}})
    return {'windows':windows,'visible_messages':len(visible),'scope':'Only messages witnessed by this agent in the current event.','topic_method':'Frequent words and phrases, extracted locally; labels are not semantic judgments.','relay_method':'Named references are reported mentions, not verified information transfers.'}
