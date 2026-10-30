"""Directed, time-windowed delivery graph using sequence membership boundaries."""
from collections import Counter,defaultdict
import math
import time

from .store import AppError


def deliveries(store, rooms, member_ids, visible_to=None):
    """One edge per other resident who actually witnessed a group message.

    Group broadcasts are not inferred one-to-one addressing or read receipts.
    Optional visibility scopes NPC attention signals to its own witnessed history.
    """
    if not rooms:
        return []
    placeholders = ','.join('?' for _ in rooms)
    with store.db() as db:
        messages = db.execute(f'''SELECT seq,conversation_id,sender_id,created_at
            FROM conversation_messages WHERE conversation_id IN ({placeholders}) ORDER BY seq''', tuple(rooms)).fetchall()
        visits = db.execute(f'SELECT * FROM conversation_visits WHERE conversation_id IN ({placeholders})', tuple(rooms)).fetchall()
    boundaries=defaultdict(list)
    for visit in visits:boundaries[(visit['conversation_id'],visit['member_id'])].append((visit['joined_after_seq'],visit['left_after_seq']))
    def witnessed(person, message):
        return any(message['seq'] > start and (finish is None or message['seq'] <= finish)
                   for start,finish in boundaries[(message['conversation_id'],person)])
    result = []
    for message in messages:
        if message['sender_id'] not in member_ids or (visible_to and not witnessed(visible_to, message)):
            continue
        for target in member_ids:
            if target != message['sender_id'] and witnessed(target, message):
                result.append({'source': message['sender_id'], 'target': target,
                               'at': message['created_at'], 'seq': message['seq']})
    return result


def communication_graph(event, viewer, window=300, offset=None):
    if viewer != event.host_id:
        raise AppError('Only the host can inspect the event communication graph', 403)
    try:
        window = float(window)
        offset = None if offset is None else float(offset)
        if not math.isfinite(window) or not 1 <= window <= 86400:
            raise ValueError()
        if offset is not None and (not math.isfinite(offset) or offset < 0):
            raise ValueError()
    except (ValueError, TypeError, OverflowError):
        raise AppError('Use a window of 1–86400 seconds and a nonnegative timeline position') from None
    with event.lock:
        state, rooms = dict(event.state), set(event.rooms)
    started = state.get('started_at') or time.time()
    latest = max(started, state.get('finished_at') or time.time())
    end = latest if offset is None else min(started + offset, latest)
    member_ids = set(event.personas)
    npc = getattr(event, 'npc', None)
    if npc and npc.enabled:
        member_ids.add(npc.member_id)
    edges = Counter((item['source'], item['target']) for item in deliveries(event.server.store, rooms, member_ids)
                    if max(started, end-window) < item['at'] <= end)
    with event.server.store.db() as db:
        names = {row['id']: row['name'] for row in db.execute('SELECT id,name FROM members')}
    names.update({member: persona['name'] for member, persona in state.get('starting_identities', {}).items()})
    return {'event_id': state['event_id'], 'started_at': started, 'latest_at': latest,
            'end_at': end, 'window_seconds': window, 'duration': latest-started,
            'live': offset is None, 'nodes': [
                {'id': member, 'name': names.get(member, 'Resident'),
                 'npc': bool(npc and member == npc.member_id),
                 'sent': sum(n for (source, _), n in edges.items() if source == member),
                 'received': sum(n for (_, target), n in edges.items() if target == member)}
                for member in sorted(member_ids)],
            'edges': [{'source': source, 'target': target, 'count': n}
                      for (source, target), n in sorted(edges.items())],
            'definition': 'A directed edge counts messages delivered to another joined participant; group messages contribute one edge per recipient. It does not prove a reply or that someone read a message.'}
