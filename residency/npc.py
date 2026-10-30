"""Low-cost, disclosed facilitator. Reads only messages it actually witnessed."""
from collections import Counter
import re
import time

from .graph import deliveries

AGREEMENT = re.compile(r'\b(i agree|we agree|agreed|exactly|absolutely|you.re right|well said|totally agree|same here|couldn.t agree more)\b', re.I)
QUALIFICATION = re.compile(r'\b(but|however|disagree|not agree|don.t agree|do not agree|not sure|except|although)\b', re.I)


def agreement_score(messages):
    """Transparent English phrase heuristic, not semantic or psychological scoring."""
    recent = messages[-4:]
    agreement = [m for m in recent if AGREEMENT.search(m['body']) and not QUALIFICATION.search(m['body'])]
    if len(recent) < 4 or len({m['sender_id'] for m in recent}) < 2 or len(agreement) < 3:
        return 0.0
    return len(agreement)/len(recent)


class Facilitator:
    def __init__(self, event, member_id, enabled=True):
        self.event, self.member_id, self.enabled = event, member_id, enabled
        self.reset()
        # Restarts/resumes preserve the per-event question cap and cooldowns.
        self.questions=list(event.state.get('npc_questions',[]))
        self.last_question={q['conversation_id']:q['at'] for q in self.questions}

    def reset(self):
        self.last_question = {}
        self.joined_at = 0
        self.questions = []
        self.last_observed = {}

    def view(self):
        return {'enabled': self.enabled, 'member_id': self.member_id,
                'question_count': len(self.questions), 'max_questions': 6,
                'agreement_minimum': '3 of the latest 4 witnessed messages, from at least 2 residents, contain unqualified English agreement phrases',
                'attention_minimum': 'At least 6 witnessed deliveries, with one resident receiving at least 60%',
                'utility': 'U = agreement score + attention concentration; questions prefer the larger signal, with a 90-second room cooldown and at most 6 questions per event.',
                'visibility': 'Joins one room at a time from public presence. No earlier messages or leave/rejoin gaps are inspected. Attention uses only witnessed deliveries.',
                'questions': list(self.questions)}

    def run(self):
        try:
            while not self.event.stop_flag.is_set():
                self.event.npc_wake.wait(1)
                self.event.npc_wake.clear()
                with self.event.lock:
                    if self.event.stop_flag.is_set() or not self.event.active:
                        break
                    self.step()
        finally:
            with self.event.lock:
                self.leave_all()

    def leave_all(self):
        rooms = [r['id'] for r in self.event.server.store.conversation_state(self.member_id)['conversations'] if r['joined']]
        for index in range(0, len(rooms), 3):
            self.event.server.store.conversation_action(self.member_id, {'leave_conversations': rooms[index:index+3]})

    def step(self, now=None):
        now = time.time() if now is None else now
        if not self.enabled or len(self.questions) >= 6:
            return
        state = self.event.server.store.conversation_state(self.member_id)
        rooms = [r for r in state['conversations'] if r['id'] in self.event.rooms
                 and 2 <= len(set(r['participants']) & self.event.personas.keys()) <= 3]
        if not rooms:
            return
        joined = next((r for r in rooms if self.member_id in r['participants']), None)
        # Rotate by public presence, never by hidden message content.
        if joined is None or now-self.joined_at >= 30:
            alternatives = [r for r in rooms if not joined or r['id'] != joined['id']]
            target = min(alternatives or rooms, key=lambda r: self.last_observed.get(r['id'], 0))
            if not joined or target['id'] != joined['id']:
                # Other residents may open new rooms with the facilitator.
                # Leave in the same bounded batches as normal shutdown.
                self.leave_all()
                self.event.server.store.conversation_action(self.member_id, {
                    'join_conversations': [target['id']]})
                self.joined_at = now
                self.last_observed[target['id']] = now
                return  # Never use the pre-join transcript to decide an intervention.
        room = joined['id']
        messages = [m for m in state['conversation_messages'] if m['conversation_id'] == room
                    and m['sender_id'] in self.event.personas and now-300 <= m['created_at'] <= now]
        agreement = agreement_score(messages)
        incoming = Counter(item['target'] for item in deliveries(
            self.event.server.store, self.event.rooms, set(self.event.personas), visible_to=self.member_id)
            if now-300 <= item['at'] <= now)
        total = sum(incoming.values())
        popular, count = incoming.most_common(1)[0] if incoming else (None, 0)
        concentration = count/total if total >= 6 and count/total >= .6 else 0
        if (not agreement and not concentration) or now-self.last_question.get(room, float('-inf')) < 90:
            return
        participants = set(joined['participants']) & self.event.personas.keys()
        if concentration > agreement and popular in participants:
            peers = sorted(participants-{popular}, key=lambda person: incoming[person])
            if not peers:
                return
            target = self.event.personas[peers[0]]['name']
            body = f'{target}, would you like to bring in a perspective or question of your own? You can also pass or explore a different subject.'
            reason = 'attention_concentration'
        elif agreement:
            body = 'What assumption here might fail in a different setting, or what experience could lead someone to a different view? You can also explore another subject if you prefer.'
            reason = 'repeated_agreement'
        else:
            return
        result = self.event.server.store.conversation_action(self.member_id, {'messages': [
            {'conversation_id': room, 'body': body}]})
        self.last_question[room] = now
        self.questions.append({'conversation_id': room, 'at': now, 'reason': reason,
                               'agreement_score': agreement, 'attention_concentration': concentration,
                               'utility': agreement+concentration, 'body': body})
        self.event.state['message_count'] += len(result['messages'])
        self.event.state['npc_questions'] = list(self.questions)
        self.event._save()
        self.event.server.capture_conversations(result['affected_members'])
        self.event.notify(set(result['affected_members'])-{self.member_id})
