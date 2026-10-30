"""Human-authored test identities; private values never enter public profiles."""
import json
import time

from .store import AppError, text

FIELDS = {
    'name': ('Name', 80), 'nickname': ('Nickname', 80), 'nationality': ('Nationality', 300), 'region': ('Region', 300),
    'cv': ('Relevant project context', 16000), 'skills': ('Skills', 2000), 'interests': ('Interests', 2000),
    'cv_notes': ('Other relevant project context', 16000),
    'subject_expertise': ('Subject expertise', 4000),
    'products_built': ('Products and projects built', 6000),
    'source_website': ('Portfolio or project website', 2000),
    'personal_offer': ('What I can offer personally', 2000),
    'personal_seeking': ('What I am looking for personally', 2000),
    'skills_offer_people': ('Skills I can offer other residents', 2000),
    'skills_need_people': ('Skills I need from other residents', 2000),
    'environment_offer': ('What I can offer the village', 2000),
    'environment_need': ('What I need from the village', 2000),
    'reciprocity': ('What I want in return', 2000),
    'moral_compass': ('Guiding moral approach', 2000),
    'political_standing': ('Political outlook (optional)', 2000),
    **{f'moral_{key}': (label, 1200) for key, label in (
        ('care', 'Care'), ('equality', 'Equality'), ('proportionality', 'Proportionality'),
        ('loyalty', 'Loyalty'), ('authority', 'Authority'), ('sanctity', 'Purity / sanctity'))},
    'introduction': ('Public introduction', 2000),
}
PRIVATE = {'moral_compass', 'political_standing', *(key for key in FIELDS if key.startswith('moral_'))}

# Original, optional multiple-choice questions inspired by MFQ-2 domains. No scoring.
QUESTIONS = {
    'moral_compass': 'Which approach most often guides your choices when important values conflict?',
    'political_standing': 'Which option comes closest to your self-described political outlook? Choose mixed/unrepresented or skip if these labels do not fit your context.',
    'moral_care': 'If a promising project could harm a few people while helping many, how would you decide whether to proceed?',
    'moral_equality': 'When a community has limited resources, what should everyone receive equally, and when might unequal access be justified?',
    'moral_proportionality': 'If people contribute different amounts of effort, expertise, or money, how should rewards and responsibilities be shared?',
    'moral_loyalty': 'If your friends or community support a decision you think is wrong, how would you respond? What would make you speak out?',
    'moral_authority': 'When should you follow a leader or community rule, and when should you challenge it? What makes authority legitimate?',
    'moral_sanctity': 'What, if anything, do you consider sacred or worth protecting from degradation? How would you handle a conflicting community preference?',
}

# Choices are descriptions of trade-offs, with no ordinal values or scores.
CHOICES = {
    'moral_compass': [
        'I start with rights and principles that should not be violated.',
        'I start with the likely benefits and harms of each choice.',
        'I start with care, relationships, and responsibilities to others.',
        'I start with community commitments and traditions.',
        'I weigh several approaches; it depends on the situation.',
        'I am unsure or still exploring my principles.',
    ],
    'political_standing': [
        'I identify mainly with progressive or left-leaning politics.',
        'I identify mainly with conservative or right-leaning politics.',
        'I identify mainly with centrist or moderate politics.',
        'I prioritise individual liberty and limited government.',
        'I prioritise ecological politics and environmental responsibility.',
        'My outlook is mixed, context-specific, or not represented here.',
        'I do not identify with a political position or am unsure.',
    ],
    'moral_care': [
        'Do not proceed while people face serious harm, even if many could benefit.',
        'Proceed only with affected people participating in the decision and strong protections.',
        'Proceed if the overall benefits outweigh the harms and those harmed receive support.',
        'It depends on the severity, alternatives, and what affected people want.',
        'I am unsure how I would decide.',
    ],
    'moral_equality': [
        'Give everyone an equal share of the limited resources.',
        'Give more to people with greater needs or fewer alternatives.',
        'Give everyone an equal minimum, then decide how to distribute the rest.',
        'Let the community agree on an allocation for this particular situation.',
        'I am unsure; I would need more context.',
    ],
    'moral_proportionality': [
        'Share rewards equally, even when contributions differ.',
        'Link rewards mainly to effort and time, including less visible work.',
        'Link rewards mainly to results and the value of contributions.',
        'Use agreed contributions while accounting for different needs and capacities.',
        'I am unsure; I would negotiate the arrangement with those involved.',
    ],
    'moral_loyalty': [
        'Support the group decision despite my disagreement.',
        'Raise concerns privately first while continuing to support the group.',
        'Speak out publicly when I believe the decision causes serious harm.',
        'Prioritise my judgment and leave or oppose the group if necessary.',
        'It depends on the issue and the risks; I am not committed to one response.',
    ],
    'moral_authority': [
        'Follow established leaders and rules unless there is clear abuse.',
        'Follow authority when it is accountable and those affected can participate.',
        'Assess each instruction independently and challenge rules I consider unjust.',
        'Prefer shared decisions with minimal hierarchy.',
        'It depends on legitimacy, expertise, and the situation; I am unsure otherwise.',
    ],
    'moral_sanctity': [
        'Protect sacred traditions or practices even when change would be convenient.',
        'Protect human dignity and bodily integrity as boundaries for community choices.',
        'Protect ecosystems and places I regard as irreplaceable.',
        'Allow people their own sacred commitments, without imposing them on others.',
        'Judge choices by harms and benefits rather than sacred boundaries.',
        'I am unsure or this concern is not central to my outlook.',
    ],
}


def validate_identity(payload):
    if not isinstance(payload, dict) or set(payload) - {*FIELDS, 'share_values', 'cv_evidence'}:
        raise AppError('Unrecognized identity fields')
    result = {key: text(payload.get(key, ''), label, maximum, key in ('name', 'introduction'))
              for key, (label, maximum) in FIELDS.items()}
    share = payload.get('share_values', False)
    if type(share) is not bool:
        raise AppError('Choose whether to share moral and political details')
    result['share_values'] = share
    if payload.get('cv_evidence'):
        from .identity_extract import validate_suggestions
        evidence = validate_suggestions({'suggestions': payload['cv_evidence']}, result['cv'])
        result['cv_evidence'] = [item for item in evidence if item['text'] in result[item['field']]]
    return result


def public_identity(identity):
    return {key: value for key, value in identity.items()
            if key not in ('share_values', 'cv_evidence') and (key not in PRIVATE or identity.get('share_values') is True)}


def markdown(value):
    """Export the saved identity in the five documented pillars, including provenance."""
    pillars = (
        ('Name', ('name','nickname')), ('Given identity', ('nationality', 'region')),
        ('Skill identity', ('cv', 'skills','subject_expertise','products_built','source_website','interests','cv_notes')),
        ('Contribution and reciprocity', ('personal_offer', 'personal_seeking', 'skills_offer_people',
            'skills_need_people', 'environment_offer', 'environment_need', 'reciprocity')),
        ('Moral compass', tuple(QUESTIONS)),
    )
    lines = ['# Identity', '', 'Private host export. Values and politics follow the sharing preference in the app.', '']
    for title, keys in pillars:
        lines += ['## '+title, '']
        for key in keys:
            lines += ['### '+FIELDS[key][0], '', value.get(key) or 'Unspecified.', '']
    lines += ['## Disclosure', '', 'Share values with residents: '+('yes' if value.get('share_values') else 'no'), '',
              '## Optional CV model context', '', 'Model interpretations and excerpts are unverified context for human review.', '']
    for item in value.get('cv_evidence', []):
        lines += ['### '+FIELDS[item['field']][0], '', item['text'], '',
                  'Model excerpt: '+json.dumps(item['quote'], ensure_ascii=False), '']
    return '\n'.join(lines)


def profile(identity):
    public = public_identity(identity)
    def combine(keys):
        return '\n'.join(f'{FIELDS[key][0]}: {public[key]}' for key in keys if public.get(key))[:2000]
    return {'name': identity['name'],
            'bio': combine(('nationality', 'region', 'cv', 'skills', 'interests')),
            'offering': combine(('personal_offer', 'skills_offer_people', 'environment_offer')),
            'seeking': combine(('personal_seeking', 'skills_need_people', 'environment_need', 'reciprocity'))}


def create_schema(store, agent_limit=3):
    with store.db() as db:
        db.executescript(f'''
            CREATE TABLE IF NOT EXISTS sandbox_owner(singleton INTEGER PRIMARY KEY CHECK(singleton=1),
                member_id TEXT NOT NULL REFERENCES members(id));
            CREATE TABLE IF NOT EXISTS agent_identities(
                slot INTEGER PRIMARY KEY CHECK(slot BETWEEN 1 AND {agent_limit}),
                member_id TEXT UNIQUE NOT NULL REFERENCES members(id),
                identity_json TEXT NOT NULL, updated_at REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS identity_revisions(
                id INTEGER PRIMARY KEY AUTOINCREMENT, slot INTEGER NOT NULL,
                identity_json TEXT NOT NULL, recorded_at REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS compass_observations(
                id INTEGER PRIMARY KEY AUTOINCREMENT, event_id TEXT NOT NULL,
                member_id TEXT NOT NULL REFERENCES members(id), message_id TEXT NOT NULL,
                label TEXT NOT NULL, quote TEXT NOT NULL, note TEXT NOT NULL, recorded_at REAL NOT NULL);
        ''')
        for table in ('agent_identities','identity_revisions'):
            if 'identity_markdown' not in {row[1] for row in db.execute('PRAGMA table_info('+table+')')}:
                db.execute('ALTER TABLE '+table+' ADD COLUMN identity_markdown TEXT')


def rows(store):
    with store.db() as db:
        return [{'slot': row['slot'], 'member_id': row['member_id'],
                 'identity': json.loads(row['identity_json']), 'updated_at': row['updated_at'],
                 'identity_markdown':row['identity_markdown']}
                for row in db.execute('SELECT * FROM agent_identities ORDER BY slot')]


def save(store, slot, member, identity, identity_markdown=None):
    now = time.time()
    with store.db() as db:
        db.execute('INSERT INTO agent_identities(slot,member_id,identity_json,updated_at,identity_markdown) VALUES(?,?,?,?,?) ON CONFLICT(slot) DO UPDATE SET identity_json=excluded.identity_json, updated_at=excluded.updated_at, identity_markdown=excluded.identity_markdown',
                   (slot, member, json.dumps(identity, ensure_ascii=False), now, identity_markdown))
        db.execute('INSERT INTO identity_revisions(slot,identity_json,recorded_at,identity_markdown) VALUES(?,?,?,?)',
                   (slot, json.dumps(identity, ensure_ascii=False), now, identity_markdown))
