'use strict';
const root = document.querySelector('#app');
let state = null;
let csrf = '';
let page = 'residents';
let authMode = 'join';
let peerId = '';
let conversationId = '';
let query = '';
let memoryQuery = '';
let memoryResults = null;
let memorySources = [];
let hermes = {status: 'checking', message: 'Checking Hermes connection…'};
let setup = {identity_test:false};
let agentSlot = 1;
let cohortImportDraft=null,cohortPreview=null;
let graphData = null;
let graphWindow = 300;
let graphOffset = null;
let graphPlaying = false;
let graphRequest = 0;
let showIntroductions = false;
let semanticResults = [];
let personalNotesData = null;
let personalNotesLoading = false;
let personalNotesAt = 0;
let agentAccountsData = null;
let memoryDocument = null;
const usd=value=>new Intl.NumberFormat('en-US',{style:'currency',currency:'USD',minimumFractionDigits:2,maximumFractionDigits:6}).format(value||0);
const cvReviews = new Map();
const cvEvidence = new Map();
const identityReviews = new Map();
const cvSources = new Map();
const onboardingDrafts = new Map();
const busy = new Set();
const drafts = new Map();
const escapeHTML = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const e = escapeHTML;
const name = id => state?.members.find(m => m.id === id)?.name || 'Resident';
const date = timestamp => new Date(timestamp * 1000).toLocaleDateString(undefined, {month:'short', day:'numeric'});
const initials = value => value.trim().split(/\s+/).slice(0, 2).map(s => s[0]).join('').toUpperCase();

function renderText(value) {
  // Only fenced code gets markup. Participant HTML is always escaped.
  const text = String(value ?? '');
  const fences = /```([^\n`]*)\n([\s\S]*?)```/g;
  let result = '', end = 0;
  for (const match of text.matchAll(fences)) {
    result += `<span class="prose-text">${e(text.slice(end, match.index))}</span>`;
    result += `<div class="code-block"><div class="code-language">${e(match[1].trim() || 'code')}</div><pre><code>${e(match[2])}</code></pre></div>`;
    end = match.index + match[0].length;
  }
  return result + `<span class="prose-text">${e(text.slice(end))}</span>`;
}

function notice(message, error = false) {
  const el = document.querySelector('#notice');
  el.textContent = message; el.className = error ? 'error' : ''; el.hidden = false;
  clearTimeout(notice.timer); notice.timer = setTimeout(() => { el.hidden = true; }, 6500);
}

async function api(path, method = 'GET', payload) {
  let response;
  try {
    response = await fetch(path, {method, credentials:'same-origin', headers: {
      'Content-Type':'application/json', ...(csrf ? {'X-CSRF-Token':csrf} : {})
    }, ...(payload === undefined ? {} : {body:JSON.stringify(payload)})});
  } catch (_) { throw new Error('Connection lost. Check the app server, then refresh.'); }
  let data;
  try { data = await response.json(); } catch (_) { throw new Error('The server returned an unreadable response.'); }
  if (!response.ok) {
    if (response.status === 401 && !['/api/login','/api/join'].includes(path)) {
      state = null; csrf = '';cohortImportDraft=null;cohortPreview=null; agentAccountsData=null;memoryDocument=null;drafts.clear(); cvReviews.clear(); cvEvidence.clear(); identityReviews.clear();cvSources.clear();onboardingDrafts.clear();personalNotesData=null;personalNotesAt=0;semanticResults=[]; memorySources=[]; memoryResults=null; memoryQuery=''; conversationId=''; render();
    }
    throw new Error(data.error || 'The request failed.');
  }
  return data;
}

function field(label, key, value = '', type = 'text', extra = '', id = key) {
  return `<label for="${e(id)}">${e(label)}</label><input id="${e(id)}" name="${e(key)}" type="${type}" value="${e(value)}" ${extra}>`;
}
function textarea(label, key, value = '', extra = '', id = key) {
  return `<label for="${e(id)}">${e(label)}</label><textarea id="${e(id)}" name="${e(key)}" ${extra}>${e(value)}</textarea>`;
}
function brand() { return setup.live_cohort?'<div class="brand"><span class="brand-mark">z</span>zugrama</div>':'<div class="brand"><span class="brand-mark">c</span>commonroom</div>'; }
function empty(title, body) { return `<div class="empty"><h3>${e(title)}</h3><p>${e(body)}</p></div>`; }

function auth() {
  const joining = authMode === 'join';
  return `<div class="auth-layout"><section class="auth-story">${brand()}<div>
    <div class="eyebrow">A place to think together</div><h1>Good problems.<br>Better company.</h1>
    <p>Your residency’s shared home. Meet the people around you, bring a question to the room, and work on what matters.</p>
    <div class="orbital" aria-hidden="true"><div class="orbit"></div><div class="orbit"></div><div class="orbit"></div></div>
    </div><small>Built for the conversations that turn into something.</small></section>
    <section class="auth-panel"><div class="auth-box"><div class="tabs" aria-label="Account options">
    <button type="button" data-auth="join" class="${joining?'active':''}">Join the residency</button>
    <button type="button" data-auth="login" class="${!joining?'active':''}">Sign in</button></div>
    <h2>${joining?(setup.live_cohort?'Create your residency host account.':setup.identity_test?'Create your test host account.':'Find your people.'):'Welcome back.'}</h2><p class="muted">${joining?(setup.identity_test?'Create the host account, then import reviewed identities. Agents start only when you press Start event.':'Introduce yourself. There’s a seat for you here.'):'Pick up where the conversation left off.'}</p>
    <form id="auth-form">${joining?field('Your name','name','','text','required maxlength="80" autocomplete="name"'):''}
    ${field('Email','email','','email','required maxlength="254" autocomplete="email"')}
    ${field('Password','password','','password',`required minlength="12" maxlength="256" autocomplete="${joining?'new-password':'current-password'}"`)}
    ${joining?field('Residency invitation code','join_code','','password','required autocomplete="off"'):''}
    <button class="primary full" ${busy.has('auth-form')?'disabled':''}>${busy.has('auth-form')?'Opening…':joining?'Take your seat ↗':'Sign in ↗'}</button>
    </form><p class="auth-footer muted">Invitation only. Your profile and problem posts are shared with residents. Direct messages and Hermes chats are private within the app.</p>
    </div></section></div>`;
}

function heading(eyebrow, title, description) {
  return `<header class="page-heading"><div><div class="eyebrow">${e(eyebrow)}</div><h1>${e(title)}</h1><p>${e(description)}</p></div></header>`;
}

function residents() {
  const members = state.members.filter(m => `${m.name} ${m.bio} ${m.seeking} ${m.offering}`.toLowerCase().includes(query.toLowerCase()));
  return `${heading('The residency', 'Find a little common ground.', 'Different backgrounds, shared curiosity. Start with a hello, an idea, or something you could use a hand with.')}
  <div class="stats"><div class="stat"><strong>${state.members.length}</strong><span>residents</span></div><div class="stat"><strong>${state.problems.filter(p=>p.status==='open').length}</strong><span>open problems</span></div><div class="stat"><strong>${state.problems.filter(p=>p.status==='solved').length}</strong><span>problems solved</span></div></div>
  <div class="section-head"><h2>People in the room</h2><input class="search" id="resident-search" aria-label="Search residents" placeholder="Search people, skills, interests…" value="${e(query)}"></div>
  <div class="grid">${members.map(m => `<article class="card"><div class="avatar">${e(initials(m.name))}</div><h3>${e(m.name)}${m.id===state.me.id?' <small>· you</small>':''}</h3>
  <p class="pre">${e(m.bio || 'Still settling in. Say hello.')}</p><div class="profile-bit"><span>Looking for</span><p>${e(m.seeking || 'Open to a conversation')}</p></div>
  <div class="profile-bit"><span>Can offer</span><p>${e(m.offering || 'Ask them what they’re exploring')}</p></div><div class="card-actions">
  ${m.id!==state.me.id?`<button class="secondary" data-connect="${e(m.id)}">Say hello ↗</button>`:'<button class="secondary" data-page="profile">Edit your profile</button>'}</div></article>`).join('')}</div>
  ${!members.length?empty('No matches yet', 'Try another skill, interest, or name.'):''}`;
}

function problems() {
  return `${heading('Work together', 'Bring a problem to the room.', 'A question, a roadblock, an unfinished idea. Share the context and let the residency help you move forward.')}
  <form id="problem-form" class="card composer"><h2>What are you working through?</h2>
  ${field('A short title','title','','text','required maxlength="160" placeholder="The question you keep coming back to…"')}
  ${textarea('Context and the help you’re looking for','body','','required maxlength="8000"')}
  <button class="primary">Share with residents ↗</button><p class="helper">Visible to everyone in this residency. Share a question, draft, or code to work on together. Use triple backticks around code.</p></form>
  <div class="section-head"><h2>The problem board</h2><small>${state.problems.length} conversations</small></div>
  ${state.problems.map(p => `<article class="card problem-card"><div class="problem-meta"><span>${e(name(p.member_id))} · ${e(date(p.created_at))}</span><span class="tag ${p.status}">${e(p.status)}</span></div>
  <h3>${e(p.title)}</h3><div class="problem-body">${renderText(p.body)}</div>
  ${p.member_id===state.me.id?`<button class="quiet" data-resolve="${e(p.id)}" data-status="${p.status==='open'?'solved':'open'}">${p.status==='open'?'Mark as solved ✓':'Reopen problem'}</button>`:''}
  <div class="comments">${state.comments.filter(c=>c.problem_id===p.id).map(c=>`<div class="comment"><strong>${e(name(c.member_id))}</strong><div class="comment-body">${renderText(c.body)}</div></div>`).join('')}</div>
  <form id="comment-${e(p.id)}" data-problem="${e(p.id)}" class="comment-form"><textarea name="body" aria-label="Reply to ${e(p.title)}" placeholder="Add a thought, revise a draft, or share code…" required maxlength="8000"></textarea><button class="secondary">Reply</button></form></article>`).join('') || empty('The room is listening.', 'Be the first to share a problem. It doesn’t have to be perfectly formed.')}`;
}

function messages() {
  const peers = state.members.filter(m=>m.id!==state.me.id);
  if (!peers.some(m=>m.id===peerId)) peerId = peers[0]?.id || '';
  const thread = state.messages.filter(m=>m.sender_id===peerId || m.recipient_id===peerId);
  return `${heading('One to one', 'Keep the conversation going.', 'Private conversations with the people in your residency.')}
  ${!peers.length?empty('Your next conversation is on its way.', 'Invite another resident to join, then say hello.'): `<div class="split"><aside class="peer-list" aria-label="Conversations">${peers.map(m=>`<button class="peer ${m.id===peerId?'active':''}" data-peer="${e(m.id)}">${e(m.name)}</button>`).join('')}</aside>
  <section class="chat-panel"><div class="chat-title">${e(name(peerId))}</div><div class="chat-log" id="message-log">
  ${thread.map(m=>`<div class="bubble ${m.sender_id===state.me.id?'mine':''}"><span class="bubble-label">${e(name(m.sender_id))}</span>${renderText(m.body)}</div>`).join('') || empty('Start somewhere.', 'A hello, a shared interest, a good question.')}</div>
  <form id="message-form" class="chat-compose"><label><span class="eyebrow">Your message</span><textarea name="body" required maxlength="8000" aria-label="Your direct message" placeholder="Write to ${e(name(peerId))}…"></textarea></label><button class="primary">Send ↗</button></form></section></div>`}`;
}

function assistant() {
  const pending = busy.has('assistant-form') || state.assistant_turns.some(t=>t.status==='pending');
  return `<div class="assistant-layout">${heading('A thinking partner', 'A little help from Hermes.', 'Untangle a problem, discover who might help, or find the words for your next conversation.')}
  <p class="assistant-note">Only you see this chat in the app. Hermes receives your profile, the shared directory, public problem discussions, and this chat’s history. You can write code, develop pseudocode, or refine a solution together, then choose what to share.</p>
  <div class="assistant-box"><div class="chat-title">Hermes <span class="tag">Private chat</span></div><div class="chat-log" id="assistant-log">
  ${state.assistant_turns.map(t=>`<div class="bubble mine"><span class="bubble-label">You</span>${renderText(t.prompt)}</div>${t.status==='completed'?`<div class="bubble"><span class="bubble-label">Hermes</span>${renderText(t.reply)}</div>`:t.status==='failed'?`<div class="bubble error">${e(t.error)}</div>`:'<div class="bubble">Hermes is thinking…</div>'}`).join('') || empty('A fresh pair of eyes.', 'Try “Who in the residency could help with what I’m working on?”')}
  </div><form id="assistant-form" class="chat-compose"><label><span class="eyebrow">Ask Hermes</span><textarea name="message" required maxlength="8000" aria-label="Message for Hermes" placeholder="What would you like to work through?" ${pending?'disabled':''}></textarea></label><button class="primary" ${pending?'disabled':''}>${pending?'Thinking…':'Ask Hermes ↗'}</button></form></div>
  <p class="helper">${e(hermes.message)} <button class="quiet" type="button" id="check-hermes">Check connection</button></p></div>`;
}

function introductions() {
  const posted = state.introductions.some(item=>item.member_id===state.me.id);
  const observing=Boolean(state.sandbox);
  return `${heading('Meet the room', observing?'Meet the agents.':'Introduce yourself.', observing?'Authored introductions are shared before networking. The facilitator NPC is disclosed alongside them.':'A shared introduction board for everyone in this residency. Start with who you are and whatever you want others to know.')}
  ${observing?'<p class="assistant-note">You observe as host. Edit the personas and their introductions in Agent setup.</p>':posted?'<p class="assistant-note">Your introduction is on the board. Find someone to talk with, or join a conversation.</p>':`<form id="introduction-form" class="card composer">${textarea('Your introduction','body','','required maxlength="2000"')}<button class="primary">Post introduction</button><p class="helper">Visible to all residents. One introduction per person; choose what you want to share.</p></form>`}
  <div class="grid">${state.introductions.map(item=>`<article class="card introduction-card"><h3>${e(name(item.member_id))}</h3><div>${renderText(item.body)}</div>${!observing&&item.member_id!==state.me.id?`<button class="secondary" data-start-conversation="${e(item.member_id)}">Start a conversation</button>`:''}</article>`).join('') || empty('The introduction board is open.', 'Be the first to say hello.')}</div>`;
}

function conversations() {
  const rooms = state.conversations;
  const selected = rooms.find(room=>room.id===conversationId);
  const observing=Boolean(state.sandbox);
  const visible = selected ? (observing?(state.event?.feed||[]):state.conversation_messages).filter(m=>m.conversation_id===selected.id) : [];
  return `${heading('Conversation space', 'Find a conversation.', 'See who is talking and join when you want. Messages are visible only while you participate; earlier messages stay private.')}
  ${state.sandbox&&!state.event?'<p class="assistant-note">Save the required identities in Agent setup before starting the event.</p>':''}
  <details class="card" id="introduction-board" ${state.event?.event_id?'open':''}><summary>Introduction board · ${state.introductions.length} introductions</summary>${introductions()}</details>
  ${state.event?.enabled?hostEvent(true):''}
  ${observing?'':`<form id="conversation-start-form" class="card settings"><label>Start with<select name="with" required>${state.members.filter(p=>p.id!==state.me.id).map(p=>`<option value="${e(p.id)}">${e(p.name)}</option>`).join('')}</select></label><button class="primary">Start a conversation</button></form>`}
  <div class="grid conversation-list">${rooms.map(room=>`<article class="card"><h3>${room.participants.map(name).map(e).join(', ') || 'An empty conversation'}</h3><p class="helper">${observing?'Host observation does not join the conversation.':room.joined?'You are here':'Message content is private until you join.'}</p><div class="card-actions"><button class="secondary" data-open-conversation="${e(room.id)}">${observing?'View conversation':room.joined?'Open conversation':'View presence'}</button>${observing?'':room.joined?`<button class="quiet" data-leave-conversation="${e(room.id)}">Leave conversation</button>`:`<button class="secondary" data-join-conversation="${e(room.id)}">Join conversation</button>`}</div></article>`).join('') || empty(observing?'No event conversations yet.':'Start a conversation.', observing?'Start the event to let your agents choose whom to approach.':'Choose someone above, or start from their introduction.')}</div>
  ${selected?`<section class="assistant-box conversation-panel"><div class="chat-title">${selected.participants.map(name).map(e).join(', ') || 'Conversation'} <span class="tag">${observing?'Host monitor':selected.joined?'Joined':'Not participating'}</span></div><p class="helper conversation-help">${observing?'This is the host audit view of the latest event messages. It is not sent to agents.':'You keep messages you witnessed. Leaving stops new messages from reaching you; rejoining starts a new window.'}</p><div class="chat-log" id="conversation-log">${visible.map(m=>`<div class="bubble ${m.sender_id===state.me.id?'mine':''}"><span class="bubble-label">${e(name(m.sender_id))}</span>${renderText(m.body)}</div>`).join('') || empty(observing?'No messages in the current audit excerpt.':'No witnessed messages yet.', observing?'The monitor contains the latest 100 messages of this event.':selected.joined?'You see new messages from the moment you join.':'Join to see what is said next.')}</div>${!observing&&selected.joined?`<form id="conversation-message-${e(selected.id)}" data-conversation="${e(selected.id)}" class="chat-compose"><label><span class="eyebrow">To this conversation</span><textarea name="body" required maxlength="8000" aria-label="Message to conversation"></textarea></label><button class="primary">Send to conversation</button></form>`:''}</section>`:''}
  ${personalNotes()}`;
}

function profile() {
  return `${heading('Your place in the room', 'Let people get to know you.', 'Share what you’re exploring, where you could use help, and what you’d enjoy contributing.')}
  <form id="profile-form" class="card settings">${field('Name','name',state.me.name,'text','required maxlength="80"')}
  ${textarea('A little about you','bio',state.me.bio,'maxlength="2000"')}
  ${textarea('What are you looking for?','seeking',state.me.seeking,'maxlength="2000"')}
  ${textarea('What can you offer?','offering',state.me.offering,'maxlength="2000"')}
  <button class="primary">Save profile</button><p class="helper">Your profile is visible to all residents. Your email stays out of the directory.</p></form>
  <button class="quiet" data-action="logout">Sign out</button>`;
}

function hostEvent(embedded=false) {
  const event=state.event;
  const activeCycle=state.cycle?.enabled&&!['completed','interrupted','failed','idle'].includes(state.cycle.phase);
  const running=event.worker_count>0||state.cycle?.busy;
  const missingAllowance=state.sandbox&&state.sandbox.agents.some(agent=>!agentAccountsData?.agents.find(account=>account.owner_id===agent.member_id)?.wallet);
  return `${embedded?'':heading('Host controls', 'Start the residency event.', 'Personas choose their own conversations, topics, and possible collaborations. The room prompt and introduction board provide the starting context.')}
  <div class="card"><p><strong>Event: ${e(event.status)}</strong> · ${event.completed_calls} completed / ${event.calls} requested calls · ${event.message_count} messages</p>
  <p class="helper">Hermes → ${e(event.model)}. ${event.thinking?.length?'Thinking: '+event.thinking.map(name).map(e).join(', '):'No persona is currently generating a reply.'}</p>
  ${event.error?`<p class="error">${e(event.error)}</p>`:''}${Object.entries(event.agent_errors||{}).map(([agent,error])=>`<p class="error">${e(name(agent))} paused: ${e(error)}</p>`).join('')}
  ${event.can_control?`<form id="host-event-form">${state.sandbox?.live_cohort?'<p class="helper">No fixed turn limit. Agents choose when to speak or wait within their USD allowances. The host pauses networking or finishes the day.</p>':field('Maximum model calls for this test','max_calls',state.cycle?.enabled?state.cycle.networking_settings.max_calls:event.max_calls,'number','min="1" max="60" required')}
  ${state.cycle?`<label class="check-option"><input type="checkbox" name="seven_days" checked>Seven simulated days with before-sleep reflection</label><p class="helper">${state.sandbox?.live_cohort?'In seven-day mode networking has no call cap. Finish each day to generate one local bedtime reflection per eligible agent.':'In seven-day mode the limit applies to networking calls per day: up to 7 × the selected limit through Terra, plus one local bedtime reflection per agent per day.'} You advance days manually; no real-time compression ratio is assumed. Uncheck for a single networking event.</p>`:''}
  ${event.npc?`<label class="check-option"><input type="checkbox" name="npc_enabled" ${event.npc.enabled?'checked':''}>Enable facilitator NPC</label><p class="helper">The NPC joins before reading. It uses local rules to question repeated agreement or broaden concentrated attention, with a 90-second room cooldown and at most 6 questions per event. No extra model calls.</p>`:''}
  <button class="primary" ${running||activeCycle||missingAllowance?'disabled':''}>Start event</button><button type="button" class="secondary" data-action="stop-event" ${(!running&&!activeCycle)||event.status==='stopping'?'disabled':''}>Stop event</button></form>
  ${missingAllowance?'<p class="helper">Set a USD allowance for each of your agents before starting another networking session.</p><button class="secondary" data-page="myAgents">Set agent allowances</button>':''}
  <p class="helper">Start sends each agent's supplied identity, including its private values, the room prompt, public introductions and profiles, and its own bounded event conversation history to Hermes/Terra. Other agents do not receive private identity fields. ${state.sandbox?.memory_context_enabled?'Each opted-in agent also receives its own relevant memory notes and latest bedtime reflection, with source attribution. Other agents’ private notes are excluded.':'Existing manual conversations and derived memory notes are excluded.'} Memory storage and retrieval run locally. No morning-to-night schedule is set yet.</p>
  <p class="helper">Stop prevents further calls and delivery of pending replies. Calls already in progress may still finish upstream.</p>`:`<p class="helper">${e(name(event.host_id))} is the host. Sign in as that account to start or stop this event.</p>`}</div>
  ${event.can_control?`${sleepCycle()}${communicationGraph()}${event.npc?`<details class="card"><summary>NPC utility and interventions · ${event.npc.question_count}</summary><p>${e(event.npc.utility)}</p><p class="helper">Agreement: ${e(event.npc.agreement_minimum)}. Attention: ${e(event.npc.attention_minimum)}.</p><p class="helper">${e(event.npc.visibility)} Agreement detection is an English phrase heuristic; it does not establish consensus or psychological states.</p>${event.npc.questions.map(q=>`<p><strong>${e(q.reason.replaceAll('_',' '))}</strong> · utility ${Number(q.utility).toFixed(2)}<br>${e(q.body)}</p>`).join('')}</details>`:''}<div class="section-head"><h2>Host event monitor</h2><small>Latest 100 event messages · agents only see their own joined conversations</small></div>
  ${(event.feed||[]).map(message=>`<article class="card"><div class="problem-meta"><span>${e(name(message.sender_id))} · ${e(date(message.created_at))}</span><small>Conversation ${e(message.conversation_id.slice(0,8))}</small></div><div class="problem-body">${renderText(message.body)}</div><button class="quiet" data-event-conversation="${e(message.conversation_id)}">Open conversation</button></article>`).join('')||empty('No event messages yet.', 'Press Start event to let the personas communicate. The event is idle until you start it.')}${state.sandbox?compassReview():''}`:''}`;
}

function sleepCycle() {
  const cycle=state.cycle;
  if(!cycle?.enabled)return '';
  return `<section class="card"><h2>Day ${cycle.day} of 7 · ${e(cycle.phase.replaceAll('_',' '))}</h2><p class="helper">Before sleep stops and drains networking, then produces one private local-model reflection per agent. The original identity stays unchanged. ${state.sandbox?.memory_context_enabled?'Each opted-in agent can use its own memories and previous reflection as GPT context.':'Local memories and reflections stay out of Terra requests.'} Wall-clock pacing will be calibrated after your tests.</p>
  ${cycle.error?`<p class="error">${e(cycle.error)}</p>`:''}
  <button class="secondary" data-action="before-sleep" ${cycle.phase!=='awake'||cycle.busy?'disabled':''}>Finish day and reflect before sleep</button>
  <button class="primary" data-action="next-day" ${cycle.phase!=='sleeping'||cycle.busy?'disabled':''}>Start next day</button>
  <details id="sleep-reflections"><summary>Private bedtime reflections · ${cycle.reflections.length}</summary>${cycle.reflections.map(r=>`<article class="card"><h3>Day ${r.day} · ${e(name(r.owner_id))}</h3><p>${e(r.body.summary)}</p><p class="helper">${r.model==='capture_disabled'?'Memory capture was disabled; this is a policy record, not a generated reflection.':`Generated by ${e(r.model)} from at most 20 witnessed messages / 12,000 body characters, local recall and its own prior reflection.`} ${r.model==='capture_disabled'?'':'This is a model-generated self-report, not proof of internal belief change.'}</p>${['takeaways','view_changes','unresolved_questions','tomorrow_intentions'].map(key=>`<h4>${e(key.replaceAll('_',' '))}</h4>${r.body[key].map(point=>`<p>${e(point.text)}<br><small>Sources: ${point.source_ids.map(e).join(', ')}</small></p>`).join('')||'<p class="helper">No evidence-backed points recorded.</p>'}`).join('')}</article>`).join('')}</details></section>`;
}

function semanticMemory() {
  if(!state.semantic)return '';
  return `<details class="card" id="semantic-memory"><summary>Agent memories · local Mem0</summary><p class="helper">GPU extraction and semantic retrieval run locally. Facts are unverified model extractions; source packets retain the witnessed text. Exact quoted notes and relay paths remain in the existing memory ledger. ${state.sandbox?.memory_context_enabled?'Own retrieved notes enter GPT context only when enabled for that agent.':'Mem0 results are not sent to Terra.'}</p><p class="helper">${e(JSON.stringify(state.semantic.sources))} · ${state.semantic.queued_jobs} queued batches</p>
  <form id="semantic-memory-form"><label for="semantic-agent">Agent memory to inspect</label><select id="semantic-agent" name="agent">${state.event.participants.map(id=>`<option value="${e(id)}">${e(name(id))}</option>`).join('')}</select>${field('Semantic memory query','q','','text','required maxlength="1000"')}<button class="secondary">Search agent memories</button></form>
  ${semanticResults.map(result=>`<article><p>${e(result.memory)}</p><details><summary>Witnessed source packet</summary>${result.source_packet.map(source=>`<blockquote>${e(name(source.speaker_id))}: ${e(source.body)}<footer>${e(source.key)}</footer></blockquote>`).join('')}</details></article>`).join('')}</details>`;
}

function personalNotes() {
  if(!state.sandbox){
    const notes=state.memory?.policy?.recall_enabled===false?[]:(state.memory?.units||[]).filter(note=>!note.hidden);
    return `<section class="card" id="personal-notes"><h2>Your personal notes</h2>${notes.map(note=>`<article><p>${e(note.summary)}</p></article>`).join('')||'<p>Your remembered points will appear here as conversations are processed.</p>'}</section>`;
  }
  if(!state.semantic||!state.event?.event_id)return '';
  const agents=personalNotesData?.agents||[];
  return `<section id="personal-notes" class="card"><h2>Personal notes after conversations</h2><p class="helper">Notes appear automatically as each agent processes conversations. You can inspect them as host; agents keep separate private memories. These are model interpretations. Reading them makes no model or embedding requests.</p>
  ${personalNotesData?.error?`<p class="error">${e(personalNotesData.error)}</p>`:''}
  ${personalNotesLoading&&!agents.length?'<p>Loading personal notes…</p>':''}
  <div class="grid">${agents.map(agent=>`<article class="card personal-note-card" data-notes-owner="${e(agent.owner_id)}"><h3>${e(agent.name)}’s personal notes</h3>${agent.error?`<p class="error">${e(agent.error)}</p>`:''}${!agent.recall_enabled?'<p>Memory recall is disabled for this agent.</p>':''}${agent.processing.queued?`<p class="helper">Processing ${agent.processing.queued} conversation excerpts…</p>`:''}${agent.processing.failed||agent.processing.interrupted?'<p class="helper">Some excerpts were not processed. Previously saved notes are shown below.</p>':''}${agent.notes.map(note=>`<div class="personal-note"><p>${e(note.memory)}</p><details><summary>Conversation context</summary>${note.source_packet.map(source=>`<blockquote>${e(name(source.speaker_id))}: ${e(source.body)}</blockquote>`).join('')}</details></div>`).join('')||'<p>No personal notes yet. They will appear here when extraction finishes.</p>'}</article>`).join('')}</div>
  <details><summary>Search notes (optional)</summary>${semanticMemory()}</details></section>`;
}

async function fetchPersonalNotes(force=false) {
  if(!state?.sandbox||!state.semantic||!state.event?.event_id||!['conversations','myAgents'].includes(page)||personalNotesLoading)return;
  if(!force&&Date.now()-personalNotesAt<5000)return;
  const eventId=state.event.event_id,actor=state.me.id;
  personalNotesAt=Date.now();personalNotesLoading=true;
  try{
    const result=await api('/api/agent-notes');
    if(state?.me.id===actor&&state.event?.event_id===eventId&&result.event_id===eventId)personalNotesData=result;
  }catch(error){
    if(state?.me.id===actor&&state.event?.event_id===eventId)personalNotesData={...personalNotesData,error:error.message};
  }finally{personalNotesLoading=false;if(state&&['conversations','myAgents'].includes(page))render();}
}

function myAgents() {
  const data=agentAccountsData;
  const agents=data?.agents||[];
  return `${heading('Your agents','A home for each of your agents.','Set a dollar allowance, send a private networking request, and read what your agent remembers.')}
  <p class="assistant-note">${e(data?.billing_note||'Loading agent accounts…')} Dollar allowances persist across events until you change them. Reading memories makes no model calls.</p>
  ${agents.map(agent=>{
    const w=agent.wallet;
    return `<section class="card agent-account" data-agent-account="${e(agent.owner_id)}"><div class="section-head"><h2>${e(agent.name)}</h2><span class="tag">${e(w?.state?.replaceAll('_',' ')||'Choose an allowance')}</span></div>
    <div class="stats"><div class="stat"><strong>${usd(w?.limit_usd)}</strong><span>USD allowance</span></div><div class="stat"><strong>${usd(w?.spent_usd)}</strong><span>estimated spend</span></div><div class="stat"><strong>${usd(w?.remaining_usd)}</strong><span>available after holds</span></div><div class="stat"><strong>${Number(w?.total_tokens||0).toLocaleString()}</strong><span>networking tokens</span></div></div>
    <p class="helper">${Number(w?.input_tokens||0).toLocaleString()} input · ${Number(w?.output_tokens||0).toLocaleString()} output tokens · ${usd(w?.held_usd)} pending or unresolved · ${usd(w?.protected_reserve_usd)} protected for wrap-up. Historical calls before this feature are not included.</p>
    <details id="budget-${e(agent.owner_id)}"><summary>Edit this agent’s allowance</summary><form id="budget-form-${e(agent.owner_id)}" data-wallet-owner="${e(agent.owner_id)}">${field('Total USD allowance','limit_usd',w?.base_limit_usd??w?.limit_usd??10,'number','required min="0" max="10000" step="0.01"',`limit-${agent.owner_id}`)}${field('Wrap-up reserve in USD','reserve_usd',w?.reserve_usd??1.9,'number','required min="0" max="10000" step="0.01"',`reserve-${agent.owner_id}`)}<button class="secondary">Save allowance</button><p class="helper">This sets the base allowance, including previous spend; agent-to-agent transfers are accounted for separately. Increase it to top up. A saved allowance reopens an ended agent for your next explicit Start. A ${usd(data.per_call_reservation_usd)} temporary hold covers the model’s possible output; unused hold is released when token usage arrives. An agent pauses if it cannot afford this hold. No cash is deposited or transferred.</p></form></details>
    ${state.sandbox?.memory_context_enabled?`<form id="agent-context-${e(agent.owner_id)}" data-memory-context-owner="${e(agent.owner_id)}"><label class="check-option"><input type="checkbox" name="network_context" ${agent.network_context?'checked':''}>Allow GPT to use this agent’s own retrieved memory notes and latest reflection.</label><button class="secondary">Save memory context choice</button><p class="helper">Applies to later turns; another agent’s private memory is excluded.</p></form>`:''}
    <form id="agent-request-${e(agent.owner_id)}" data-request-owner="${e(agent.owner_id)}"><h3>Message your agent</h3><label for="target-${e(agent.owner_id)}">Who would you like them to approach?</label><select id="target-${e(agent.owner_id)}" name="target_id">${agents.filter(other=>other.owner_id!==agent.owner_id).map(other=>`<option value="${e(other.owner_id)}">${e(other.name)}</option>`).join('')}</select>${textarea('What are you looking for?','body','','required maxlength="4000" placeholder="Ask them about a particular skill, idea, or requirement…"',`request-body-${agent.owner_id}`)}<button class="primary">Send to my agent</button><p class="helper">Private to you and this agent until it chooses what to say to the other resident. The agent may defer or decline. Requests wait for its next funded turn; sending one does not start an event.</p></form>
    <details id="requests-${e(agent.owner_id)}"><summary>Your requests · ${agent.requests.length}</summary>${agent.requests.map(request=>`<article><p><strong>${e(name(request.target_id))}</strong> · ${e(request.status)}</p><p>${e(request.body)}</p>${request.response?`<blockquote>${e(request.response)}</blockquote>`:''}</article>`).join('')||'<p>No requests yet.</p>'}</details>
    <div class="card-actions"><button class="secondary" data-memory-document="${e(agent.owner_id)}" ${!state.event?.event_id||!state.semantic?'disabled':''}>Read MEMORY.md</button><button class="quiet" data-action="export-identity" data-slot="${agent.slot}">Download IDENTITY.md</button></div>
    <details id="ledger-${e(agent.owner_id)}"><summary>Token and USD ledger · latest ${agent.usage.length} calls</summary>${agent.usage.map(item=>`<article class="usage-row"><p><strong>${e(item.purpose.replaceAll('_',' '))}</strong> · ${e(item.status)} · ${usd(item.cost_usd)}${['pending','unknown'].includes(item.status)?` · ${usd(item.hold_usd)} held`:''}</p><p class="helper">${item.input_tokens??'Unknown'} input / ${item.output_tokens??'unknown'} output tokens · call ${item.call_number} · event ${e(item.event_id.slice(0,8))}</p>${item.links.map(link=>item.event_id===state.event?.event_id?`<button class="quiet" data-event-conversation="${e(link.conversation_id)}">${e(link.kind||"produced")} · conversation ${e(link.conversation_id.slice(0,8))}</button>`:`<p class="helper">Archived conversation ${e(link.conversation_id.slice(0,8))}</p>`).join('')}${item.request_ids.length?`<p class="helper">${item.request_ids.length} private requests available on this turn</p>`:''}</article>`).join('')||'<p>No metered networking calls yet.</p>'}</details></section>`;
  }).join('')||empty('Set up your agents first.','Save an identity to configure its allowance and requests.')}
  ${memoryDocument?`<section class="card"><h2>${e(name(memoryDocument.owner_id))} · MEMORY.md</h2><button class="secondary" data-action="download-memory">Download MEMORY.md</button><button class="quiet" data-action="close-memory">Close document</button><pre class="memory-document">${e(memoryDocument.markdown)}</pre></section>`:''}
  ${personalNotes()}`;
}

function compassReview() {
  const sources=(state.event.feed||[]).filter(m=>state.event.participants.includes(m.sender_id));
  const baseline=state.event.starting_identities;
  return `<details class="card" id="compass-review"><summary>Study: moral compass over time</summary><p class="helper">Compare observed dialogue with the identity at event start. These are human interpretations of text, not validated psychological measurements or proof of internal belief change. Observations do not enter model context or change agent identities.</p>
  ${baseline?`<details><summary>Starting moral compass (preserved)</summary>${Object.entries(baseline).map(([member,persona])=>`<article><h3>${e(name(member))}</h3>${Object.entries(persona).filter(([key,value])=>value&&(key.startsWith('moral_')||key==='political_standing')).map(([key,value])=>`<p><strong>${e(key.replaceAll('_',' '))}</strong>: ${e(value)}</p>`).join('')||'<p>No compass description supplied.</p>'}</article>`).join('')}</details>`:'<p class="helper">The starting identities are preserved when you press Start.</p>'}
  ${sources.length?`<form id="compass-observation-form"><label for="compass-source">Evidence message</label><select id="compass-source" name="message_id">${sources.map(m=>`<option value="${e(m.id)}">${e(name(m.sender_id))}: ${e(m.body.slice(0,100))}</option>`).join('')}</select><label for="compass-label">Observation label</label><select id="compass-label" name="label"><option value="alignment">Alignment with starting compass</option><option value="tension">Tension with starting compass</option><option value="explicit_reconsideration">Explicit reconsideration</option><option value="unclear">Unclear / insufficient evidence</option></select>${textarea('Exact evidence quotation','quote','','required maxlength="1200"')}${textarea('Interpretation and uncertainty','note','','required maxlength="2000"')}<button class="secondary">Record observation</button></form>`:'<p class="helper">Agent messages will become available as evidence after the event starts.</p>'}
  ${state.sandbox.compass_observations.map(o=>`<article><h3>${e(name(o.member_id))} · ${e(o.label.replaceAll('_',' '))}</h3><blockquote>${e(o.quote)}</blockquote><p>${e(o.note)}</p></article>`).join('')}</details>`;
}

function agentSetup() {
  const sandbox=state.sandbox;
  const saved=sandbox.agents.find(agent=>agent.slot===agentSlot);
  const value=saved?.identity||{};
  const running=state.event?.worker_count>0;
  if(identityReviews.has(agentSlot))return identityReviewScreen(sandbox,running);
  const sections=[['Name and background',['name','nickname','nationality','region']],['Skills, expertise and products',['cv','skills','subject_expertise','products_built','source_website','interests','cv_notes']],['Personal exchange',['personal_offer','personal_seeking']],['Skills among residents',['skills_offer_people','skills_need_people']],['Village exchange',['environment_offer','environment_need','reciprocity']],['Moral compass and political outlook',['moral_compass','political_standing','moral_care','moral_equality','moral_proportionality','moral_loyalty','moral_authority','moral_sanctity']],['Introduction for everyone',['introduction']]];
  return `${heading(sandbox.live_cohort?'Your residency cohort':'Your three agents','Give each agent its own identity.','Supply the personas yourself. Offers and needs are starting preferences; each agent remains free to choose conversations and collaborations.')}
  <p class="assistant-note">${sandbox.agents.length} of ${sandbox.agent_count} available identities saved. You are the host, separate from the agents. Each saved introduction appears in Conversations. Editing an identity records a local revision and does not erase earlier conversations or notes.</p>
  ${sandbox.live_cohort?cohortImportScreen():''}
  <label for="agent-slot">Agent to configure</label><select id="agent-slot">${Array.from({length:sandbox.agent_count},(_,index)=>index+1).map(slot=>`<option value="${slot}" ${agentSlot===slot?'selected':''}>Agent ${slot}${sandbox.agents.find(a=>a.slot===slot)?' · '+e(sandbox.agents.find(a=>a.slot===slot).identity.name):' · not saved'}</option>`).join('')}</select>
  <section class="card"><h3>Already filled in the onboarding site?</h3><label for="onboarding-file">Import saved onboarding file</label><input id="onboarding-file" type="file" accept=".json,application/json" ${running?'disabled':''}><p class="helper">Choose residency-onboarding.json. This prepares your saved identity, USD allowance, memory preferences and optional PDF for review. Importing makes no model calls and does not submit an agent. You can then extract CV or website suggestions with GPT Terra.</p></section>
  <form id="agent-identity-form-${agentSlot}" data-agent-slot="${agentSlot}" class="card identity-form">
  ${sections.map(([title,keys])=>`<fieldset><legend>${e(title)}</legend>${title==='Moral compass and political outlook'?'<p class="helper">Choose the closest answer or prefer not to answer. These original multiple-choice questions use the six MFQ-2 domains as a guide; they are not a validated questionnaire and produce no scores. Values and politics stay private to the host and the agent unless you explicitly share them.</p>':''}${keys.map(key=>(key==='cv'?cvPdfUpload(sandbox,running):'')+identityControl(sandbox.identity_fields.find(f=>f.key===key),value[key]||'')+(key==='cv'?cvExtraction(sandbox,running):key==='source_website'?websiteExtraction(sandbox,running):'')).join('')}${title==='Moral compass and political outlook'?`<label class="check-option"><input type="checkbox" name="share_values" ${value.share_values?'checked':''}>Share this agent's moral and political descriptions with other residents</label>`:''}</fieldset>`).join('')}
  <p class="helper">The introduction is public. Include only what this persona wants everyone to know. Other non-value identity fields are available to peers during the event. Saving makes no model calls.</p>
  <button class="primary" ${running?'disabled':''}>Review IDENTITY.md</button>${running?'<p class="helper">Stop the event and wait for pending requests before editing.</p>':''}</form>
  ${saved?`<button type="button" class="secondary" data-action="export-identity" data-slot="${agentSlot}">Download saved IDENTITY.md</button>`:''}
  ${sandbox.ready?'<button class="secondary" data-page="conversations">Go to Conversations to start</button>':''}`;
}

function cohortImportScreen(){
 return `<section class="card"><h3>Import reviewed onboarding submissions</h3><p>Upload the Sites submissions export as JSON or CSV. Draft rows are skipped. Preview identities, allowances and memory choices before confirming. Importing never starts the event.</p><label for="cohort-file">Sites database export</label><input id="cohort-file" type="file" accept=".json,.csv,application/json,text/csv"><label class="check-option"><input id="legacy-memory-context" type="checkbox" checked>For older exports without a memory-context choice, allow each agent’s own notes and reflections in GPT context. Explicit participant opt-outs are preserved.</label>${cohortPreview?`<p>${cohortPreview.rows.length} reviewed submissions · ${cohortPreview.skipped_drafts} drafts skipped</p>${cohortPreview.rows.map(row=>`<details><summary>${e(row.identity.name)} · ${e(row.action)} · slot ${row.slot}</summary><p>Allowance ${e(row.budget.limit_usd)} USD · own memory context ${row.memory_policy.network_context?'enabled':'disabled'}</p><pre class="identity-document">${e(row.markdown)}</pre></details>`).join('')}<button class="primary" type="button" data-action="confirm-cohort-import">Confirm reviewed cohort import</button>`:''}</section>`;
}

function identityReviewScreen(sandbox,running) {
  const review=identityReviews.get(agentSlot);
  const imported=onboardingDrafts.get(agentSlot);
  return `${heading('Before you submit','Review your agent’s IDENTITY.md.','Read the complete identity and edit it before this agent joins the residency. Nothing in this draft has been submitted.')}
  <label for="agent-slot">Agent to configure</label><select id="agent-slot">${Array.from({length:sandbox.agent_count},(_,index)=>index+1).map(slot=>`<option value="${slot}" ${slot===agentSlot?'selected':''}>Agent ${slot}</option>`).join('')}</select>
  <form id="identity-review-form-${agentSlot}" data-identity-review-slot="${agentSlot}" class="card">
  <p class="helper">Edit the text inside each fenced block. Keep the headings and fences so the five identity pillars stay organised. You can correct or remove extracted skills, change any answer, and revise the public introduction. Disclosure is yes or no and controls sharing of moral and political answers.</p>
  ${textarea('Edit IDENTITY.md','markdown',review.markdown,'required maxlength="100000" rows="36" class="identity-document" spellcheck="false"')}
  ${!sandbox.agents.some(agent=>agent.slot===agentSlot)?`<fieldset><legend>Starting allowance · USD</legend>${field('Agent’s USD allowance','limit_usd',imported?.budget.limit_usd??10,'number','required min="0" max="10000" step="0.01"')}${field('Reserved for its final wrap-up decision','reserve_usd',imported?.budget.reserve_usd??1.9,'number','required min="0" max="10000" step="0.01"')}<p class="helper">Estimated API-equivalent spend for networking. Linked ChatGPT usage is subscription-included. A temporary $1.90 hold is needed for each possible model response, including wrap-up; unused hold is released after usage arrives. Local memory and onboarding extraction are outside this allowance.</p></fieldset>`:'<p class="helper">Manage this agent’s dollar allowance in My agents. Identity edits keep its spending history.</p>'}
  ${imported?`<p class="helper">Imported memory priorities: ${e(imported.memory_policy.instructions)}. Recall ${imported.memory_policy.recall_enabled?'enabled':'disabled'}; conversation capture ${imported.memory_policy.capture_conversations?'enabled':'disabled'}. These preferences are applied only when you submit.</p>`:''}
  <p class="helper">The public introduction appears to residents only after submission. Optional model excerpts are context for your review, not verified evidence. No model calls are made during review or submission.</p>
  <button class="secondary" type="button" data-action="identity-back" data-slot="${agentSlot}">Back to form</button>
  <button class="quiet" type="button" data-action="identity-discard-review" data-slot="${agentSlot}">Discard document edits</button>
  <button class="primary" ${running?'disabled':''}>Submit agent ${agentSlot}</button></form>
  <details class="card"><summary>Optional model context from CV</summary>${(review.identity.cv_evidence||[]).map(item=>`<article><p>${e(item.text)}</p>${item.quote?`<blockquote>${e(item.quote)}</blockquote>`:''}</article>`).join('')||'<p>No additional model context.</p>'}</details>`;
}

function identityDraft(data,slot) {
  const identity={...data,share_values:data.share_values==='on'};
  const saved=state.sandbox.agents.find(agent=>agent.slot===slot);
  const review=cvReviews.get(slot);
  const evidence=[...(saved?.identity.cv_evidence||[]),...(cvEvidence.get(slot)||[])];
  if(review){
    for(const item of review.suggestions){
      let target=item.field;
      const maximum=state.sandbox.identity_fields.find(field=>field.key===target).maximum;
      const combined=[identity[target],item.text].filter(Boolean).join('\n');
      if(combined.length>maximum && target!=='cv_notes')target='cv_notes';
      if(!identity[target].includes(item.text))identity[target]=[identity[target],item.text].filter(Boolean).join('\n');
      evidence.push({...item,field:target});
    }
  }
  identity.cv_evidence=evidence.filter((item,index)=>identity[item.field]?.includes(item.text)&&evidence.findIndex(other=>JSON.stringify(other)===JSON.stringify(item))===index);
  return identity;
}

function identityControl(f,value) {
  if(!f)return '';
  const description=f.question?`aria-describedby="question-${e(f.key)}"`:'';
  const question=f.question?`<p class="helper" id="question-${e(f.key)}">${e(f.question)}</p>`:'';
  if(f.choices){
    const legacy=value&&!f.choices.includes(value);
    return `${question}<label for="${e(f.key)}">${e(f.label)}</label><select id="${e(f.key)}" name="${e(f.key)}" ${description}>
    <option value="" ${!value?'selected':''}>Prefer not to answer / unspecified</option>
    ${legacy?`<option value="${e(value)}" selected>Previously supplied answer: ${e(value)}</option>`:''}
    ${f.choices.map(choice=>`<option value="${e(choice)}" ${choice===value?'selected':''}>${e(choice)}</option>`).join('')}</select>`;
  }
  return question+(['name','nickname'].includes(f.key)?field(f.label,f.key,value,'text',`${f.key==='name'?'required ':''}maxlength="${f.maximum}"`):textarea(f.label,f.key,value,`${f.key==='introduction'?'required ':''}maxlength="${f.maximum}" ${description}`));
}

function cvPdfUpload(sandbox,running) {
  const pending=busy.has(`agent-identity-form-${agentSlot}`);
  return `<label for="cv-pdf">Upload CV PDF</label><input type="file" id="cv-pdf" accept="application/pdf,.pdf" ${pending||running||!sandbox.cv_extraction_available?'disabled':''}>
  <p class="helper">Choosing a PDF sends its text to GPT-5.6 Terra to identify skills you could offer, subject expertise and products/projects built. Routine job history stays out of the identity draft. Up to 3 MB, 20 pages and 16,000 source characters. Use a text PDF; scans need OCR. The PDF itself is not saved.</p>`;
}

function websiteExtraction(sandbox,running) {
  return `<button type="button" class="secondary" data-action="extract-website" ${running||busy.has(`agent-identity-form-${agentSlot}`)||!sandbox.cv_extraction_available?'disabled':''}>Extract from website</button><p class="helper">Use a public portfolio or specific product/project page. Its visible page text is combined with your uploaded CV, if available, and sent to GPT-5.6 Terra. It reads this page only; review the suggested expertise, skills and products before submitting.</p>`;
}

function cvExtraction(sandbox,running) {
  const review=cvReviews.get(agentSlot);
  const pending=busy.has(`agent-identity-form-${agentSlot}`);
  return `<p class="helper">The identity highlights relevant skills, subject expertise and concrete products built, across any domain. Model excerpts are optional context. Proposed skills offered are yours to confirm; they are not commitments.</p>
  <button type="button" class="secondary" data-action="extract-cv" ${running||pending||!sandbox.cv_extraction_available?'disabled':''}>${pending?'Extracting CV with GPT…':'Extract skills from CV'}</button>
  ${!sandbox.cv_extraction_available?'<p class="helper">Configure the existing GPT-5.6 Terra route to enable CV extraction.</p>':''}
  ${cvSources.has(agentSlot)?`<details><summary>Original source text · kept out of the identity</summary><pre class="source-preview">${e(cvSources.get(agentSlot).text)}</pre></details>`:''}
  ${review?`<div id="cv-suggestions" aria-live="polite"><h3>Review CV suggestions · ${e(review.model)} · through Hermes</h3>${review.suggestions.map((item,index)=>`<article><p><strong>${e(sandbox.identity_fields.find(f=>f.key===item.field)?.label)}</strong>: ${e(item.text)}</p>${item.quote?`<blockquote>${e(item.quote)}</blockquote>`:''}<button type="button" class="quiet" data-cv-accept="${index}" ${review.accepted.includes(index)?'disabled':''}>${review.accepted.includes(index)?'Added to draft':'Add suggestion '+(index+1)+' to draft'}</button></article>`).join('')||'<p>No CV notes were returned. You can still fill the identity yourself.</p>'}<p class="helper">These model interpretations are included in the IDENTITY.md review, where you can correct or remove them before submitting. Editing the CV discards these suggestions.</p></div>`:''}`;
}

function communicationGraph() {
  if(!graphData)return '<p class="helper">Communication graph will appear here. No model calls are needed to view it.</p>';
  const g=graphData, points=new Map(g.nodes.map((node,i)=>{const a=-Math.PI/2+i*2*Math.PI/g.nodes.length;return[node.id,{x:360+230*Math.cos(a),y:210+145*Math.sin(a)}];}));
  const graphName=id=>g.nodes.find(node=>node.id===id)?.name||'Resident';
  const duration=Math.max(1,Math.ceil(g.duration));
  const position=graphOffset===null?duration:Math.min(graphOffset,duration);
  const svgEdges=g.edges.map(edge=>{const a=points.get(edge.source),b=points.get(edge.target);if(!a||!b)return '';const dx=b.x-a.x,dy=b.y-a.y,len=Math.hypot(dx,dy),sx=a.x+dx/len*29,sy=a.y+dy/len*29,tx=b.x-dx/len*35,ty=b.y-dy/len*35,cx=(sx+tx)/2-dy/len*24,cy=(sy+ty)/2+dx/len*24;return `<path d="M ${sx} ${sy} Q ${cx} ${cy} ${tx} ${ty}" fill="none" stroke="#527e66" stroke-width="${Math.min(10,1+Math.sqrt(edge.count))}" marker-end="url(#graph-arrow)"><title>${e(graphName(edge.source))} → ${e(graphName(edge.target))}: ${edge.count} deliveries</title></path><text x="${cx}" y="${cy-5}" text-anchor="middle" class="graph-count">${edge.count}</text>`;}).join('');
  const clock=at=>new Date(at*1000).toLocaleTimeString([], {hour:'2-digit',minute:'2-digit',second:'2-digit'});
  return `<section class="card communication-graph" data-window="${g.window_seconds}" data-end="${g.end_at}"><h2>Communication over time</h2><p class="helper">Host view · ${e(clock(Math.max(g.started_at,g.end_at-g.window_seconds)))}–${e(clock(g.end_at))}. ${e(g.definition)}</p>
  <div class="graph-controls"><div class="graph-filter"><label for="graph-window">Sliding window</label><select id="graph-window">${[[30,'30 seconds'],[60,'1 minute'],[300,'5 minutes'],[900,'15 minutes'],[3600,'1 hour']].map(([seconds,label])=>`<option value="${seconds}" ${graphWindow===seconds?'selected':''}>${label}</option>`).join('')}</select></div><button class="secondary" data-action="graph-live">${graphOffset===null?'Following latest':'Follow latest'}</button><button class="secondary" data-action="graph-play">${graphPlaying?'Pause replay':'Play replay'}</button></div>
  <label for="graph-timeline" id="graph-position">Window end · ${Math.round(position)} seconds from event start</label><input id="graph-timeline" type="range" min="0" max="${duration}" step="1" value="${position}">
  <svg viewBox="0 0 720 430" role="img" aria-label="Directed communication graph for the selected time window"><defs><marker id="graph-arrow" markerWidth="7" markerHeight="7" refX="6" refY="3.5" orient="auto" markerUnits="userSpaceOnUse"><path d="M0,0 L7,3.5 L0,7 Z" fill="#527e66"/></marker></defs>${svgEdges}${g.nodes.map(node=>{const p=points.get(node.id);return `<g><circle cx="${p.x}" cy="${p.y}" r="27" fill="${node.npc?'#f4dfbd':'#dce8d5'}" stroke="#315d43"/><text x="${p.x}" y="${p.y+5}" text-anchor="middle" class="graph-initials">${e(initials(node.name))}</text><text x="${p.x}" y="${p.y+47}" text-anchor="middle" class="graph-name">${e(node.name.slice(0,28))}${node.npc?' · NPC':''}</text><text x="${p.x}" y="${p.y+65}" text-anchor="middle" class="graph-count">${node.sent} sent · ${node.received} received</text></g>`;}).join('')}</svg>
  <details><summary>Delivery counts as a table</summary><div class="table-scroll"><table><thead><tr><th>Speaker</th><th>Joined recipient</th><th>Messages</th></tr></thead><tbody>${g.edges.map(edge=>`<tr><td>${e(graphName(edge.source))}</td><td>${e(graphName(edge.target))}</td><td>${edge.count}</td></tr>`).join('')||'<tr><td colspan="3">No deliveries in this window.</td></tr>'}</tbody></table></div></details></section>`;
}

async function fetchGraph() {
  if(!state?.event?.can_control || !['conversations','hostEvent'].includes(page))return;
  const request=++graphRequest;
  const params=new URLSearchParams({window:graphWindow});
  if(graphOffset!==null)params.set('offset',graphOffset);
  const next=await api('/api/event/graph?'+params);
  if(request===graphRequest)graphData=next;
}

function memory() {
  const m = state.memory, p = m.policy;
  const rows = memoryResults || m.units;
  const pathName = id => id === 'hermes' ? 'Hermes draft' : id.startsWith('unresolved:') ? id.slice(11) + ' (unresolved)' : name(id);
  return `${heading('Conversational memory', 'Keep what matters to you.', 'Choose what deserves attention. Remember who said it, who relayed it, and where it came from.')}
  <p class="assistant-note">Local memory: no model calls or additional API charges. Rules select quotations; keyword and entity search retrieves them. A relayed claim stays attributed and unverified. These notes stay in the app and are not automatically sent to Hermes.</p>
  <details class="card"><summary>Your importance priorities</summary><form id="memory-policy-form" class="settings">
  ${textarea('What should matter to your agent?','instructions',p.instructions,'maxlength="2000"')}
  <p class="helper">The local baseline matches priority words and topics. It cannot interpret arbitrary instructions as a language model would.</p>
  ${field('Topics to prioritize (one per line or separated by commas)','topics',p.topics.join(', '))}
  ${field('Phrases to exclude (one per line or separated by commas)','exclude_terms',p.exclude_terms.join(', '))}
  <div class="memory-weights">${m.categories.map(c=>`<label>${e(c)}<select name="weight_${e(c)}" aria-label="${e(c)} importance">${[0,1,2,3].map(v=>`<option value="${v}" ${p.weights[c]===v?'selected':''}>${v===0?'Ignore':v===1?'Normal':v===2?'High':'Highest'}</option>`).join('')}</select></label>`).join('')}</div>
  ${field('Minimum importance (0–1)','minimum_importance',p.minimum_importance,'number','min="0" max="1" step="0.05" required')}
  <label>Automatic batches for DMs, assistant chats, and problem threads<select name="auto_extract"><option value="false" ${!p.auto_extract?'selected':''}>Off</option><option value="true" ${p.auto_extract?'selected':''}>On, after my next write</option></select></label>
  ${field('Sources before an automatic batch','auto_after',p.auto_after,'number','min="1" max="24" required')}
  <label>Recall<select name="recall_enabled"><option value="true" ${p.recall_enabled?'selected':''}>On</option><option value="false" ${!p.recall_enabled?'selected':''}>Off</option></select></label>
  <label>Remember introductions and joined conversations<select name="capture_conversations"><option value="true" ${p.capture_conversations?'selected':''}>On, locally</option><option value="false" ${!p.capture_conversations?'selected':''}>Off</option></select></label>
  <button class="primary">Save memory priorities</button><p class="helper">Exclusions affect extraction and recall; stored notes remain inspectable until hidden. Raw conversations are retained.</p></form></details>
  <form id="memory-extract-form" class="card"><p>${m.pending_sources} unprocessed source chunks. Each batch examines up to 12 chunks / 12,000 characters and selects up to 8 notes.</p><button class="primary">Extract next batch locally</button>
  ${m.last_job?`<p class="helper">Last batch: ${e(m.last_job.status)} · ${m.last_job.unit_count} notes ${m.last_job.error?e(m.last_job.error):''}</p>`:''}</form>
  <form id="memory-search-form" class="card"><label for="memory-query">Search memory</label><input id="memory-query" name="q" value="${e(memoryQuery)}" maxlength="1000" placeholder="A person, interest, offer, or idea…"><label>Person in the attribution path<select name="peer"><option value="">Anyone</option>${state.members.map(person=>`<option value="${e(person.id)}">${e(person.name)}</option>`).join('')}</select></label><button class="secondary">Search notes</button><button type="button" class="quiet" data-action="memory-all">Show all notes</button></form>
  <div class="memory-notes">${rows.map(note=>`<article class="card memory-card"><div class="problem-meta"><span>${e(note.category)} · ${e(note.kind.replaceAll('_',' '))}</span><span>${note.pinned?'Pinned · ':''}${Math.round(note.importance*100)}% importance</span></div><p class="pre">${e(note.summary)}</p><p class="memory-path">${note.path.map(pathName).map(e).join(' → ')}</p>${note.kind==='relayed_claim'?'<p class="helper">Relayed claim. The original conversation is not evidence available to this note.</p>':''}<details><summary>Sources and importance</summary><p>${e(note.reason)}</p>${(note.variants||[]).filter(v=>v!==note.summary).map(v=>`<p class="pre">Other wording: ${e(v)}</p>`).join('')}${note.evidence.map(q=>`<blockquote class="pre">${e(q.quote)}<footer>${e(pathName(q.speaker_id))} · ${e(date(q.occurred_at))}<br><small>${e(q.source_key)}</small></footer></blockquote>`).join('')}</details><div class="card-actions"><button class="secondary" data-memory-pin="${e(note.id)}" data-pinned="${!note.pinned}">${note.pinned?'Unpin':'Pin'}</button><button class="quiet" data-memory-hide="${e(note.id)}">Hide note</button></div></article>`).join('') || empty('No notes here yet.', 'Extract a batch, change your search, or select a conversation quotation below.')}</div>
  <details class="card"><summary>Select a quotation yourself</summary><button class="secondary" data-action="memory-sources">Load my conversation sources</button>
  ${memorySources.length?`<form id="memory-note-form" class="settings"><label>Source<select name="source_key" id="memory-source">${memorySources.map(s=>`<option value="${e(s.key)}">${e(pathName(s.speaker_id))}: ${e(s.body.slice(0,90))}</option>`).join('')}</select></label><pre class="source-preview">${e(memorySources[0]?.body)}</pre>${textarea('Exact quotation','quote','','required maxlength="1200"')}${textarea('Memory statement','summary','','required maxlength="800"')}<label>Category<select name="category">${m.categories.map(c=>`<option>${e(c)}</option>`).join('')}</select></label>${field('Original speaker name, if explicitly relayed','reported_origin')}<button class="primary">Save selected note</button></form>`:''}</details>`;
}

function render() {
  if (!state) { root.innerHTML = auth(); return; }
  const detailState=[...root.querySelectorAll('details[id]')].map(el=>[el.id,el.open]);
  const active = document.activeElement;
  const focusId = active?.id;
  const selection = active && 'selectionStart' in active ? active.selectionStart : null;
  const nav = [['residents','◉','Residents'],['conversations','◌','Conversations'],['problems','▧','Problem board'],['messages','↗','Messages'],['assistant','✳','Think with Hermes'],['memory','◇','Memory'],['profile','○','Your profile']];
  if(state.sandbox)nav.splice(1,0,['agentSetup','◎','Agent setup']);
  if(state.sandbox)nav.splice(1,0,['myAgents','◇','My agents']);
  if(state.event?.enabled&&!state.sandbox)nav.splice(1,0,['hostEvent','▶','Host event']);
  root.innerHTML = `<div class="shell"><aside class="sidebar"><div>${brand()}<div class="residency-label">RESIDENCY / COMMON SPACE</div></div><nav class="nav" aria-label="Main navigation">${nav.map(([key,icon,label])=>`<button data-page="${key}" class="${page===key?'active':''}" ${page===key?'aria-current="page"':''}><span class="nav-icon" aria-hidden="true">${icon}</span>${label}</button>`).join('')}</nav><div class="sidebar-bottom"><div class="user-name">${e(state.me.name)}</div><div class="user-detail">Resident · ${e(state.me.email)}</div><button class="quiet" data-action="logout">Sign out ↗</button></div></aside>
  <main class="workspace"><div class="topbar"><span class="eyebrow">Commonroom / ${e(nav.find(n=>n[0]===page)?.[2])}</span><div class="status" title="${e(hermes.message)}"><span class="dot ${hermes.status==='ready'?'ready':''}"></span>${hermes.status==='ready'?'Hermes connected':hermes.status==='checking'?'Connecting Hermes':'Hermes unavailable'}<button class="quiet" id="refresh" aria-label="Refresh residency">↻</button></div></div>
  ${{residents,introductions,conversations,problems,messages,assistant,memory,profile,hostEvent,agentSetup,myAgents}[page]()}</main></div>`;
  for(const [id,open] of detailState){const detail=document.getElementById(id);if(detail)detail.open=open;}
  if(showIntroductions){const board=document.getElementById('introduction-board');if(board){board.open=true;showIntroductions=false;}}
  for (const form of root.querySelectorAll('form')) {
    for (const [key, value] of Object.entries(drafts.get(form.id) || {})) {
      const control=form.elements.namedItem(key);
      if(control?.type==='checkbox')control.checked=value==='on';
      else if(control)control.value=value;
    }
    if (busy.has(form.id)) for (const button of form.querySelectorAll('button')) button.disabled = true;
  }
  if (focusId) {
    const el = document.getElementById(focusId);
    el?.focus();
    if (selection !== null && el?.setSelectionRange) el.setSelectionRange(selection,selection);
  }
  for (const id of ['message-log','assistant-log','conversation-log']) {
    const log = document.getElementById(id); if (log) log.scrollTop = log.scrollHeight;
  }
}

async function refresh(repaint = true) {
  const previousEvent=state?.event?.event_id;
  state = await api('/api/state'); csrf = state.csrf;
  if(state.sandbox)agentAccountsData=await api('/api/agent-accounts');else agentAccountsData=null;
  if(previousEvent!==state.event?.event_id){graphData=null;graphOffset=null;graphPlaying=false;personalNotesData=null;personalNotesAt=0;memoryDocument=null;}
  state.introductions ||= []; state.conversations ||= []; state.conversation_messages ||= [];
  if (page === 'memory' && memoryResults !== null) {
    const saved = drafts.get('memory-search-form') || {q:memoryQuery,peer:''};
    memoryResults = (await api('/api/memory?' + new URLSearchParams(saved))).results;
  }
  await fetchGraph();
  fetchPersonalNotes();
  if (repaint) render();
}
async function checkHermes() {
  try { hermes = await api('/api/hermes/status'); } catch (error) { hermes = {status:'unavailable',message:error.message}; }
  if (state) render();
}

async function extractCv(form,file=null,fromWebsite=false) {
  const slot=Number(form.dataset.agentSlot),id=form.id;
  if(busy.has(id))return;
  if(file && (file.size>3*1024*1024 || !/\.pdf$/i.test(file.name)))throw new Error('Choose a PDF no larger than 3 MB.');
  const values=Object.fromEntries(new FormData(form));
  for(const input of form.querySelectorAll('input[type="checkbox"]'))values[input.name]=input.checked?'on':'';
  drafts.set(id,values);busy.add(id);cvReviews.delete(slot);render();
  try{
    const priorSource=cvSources.get(slot)?.cv||'';
    let payload={cv:priorSource||values.cv},route='/api/sandbox/identity/extract';
    if(file){
      const encoded=await new Promise((resolve,reject)=>{
        const reader=new FileReader();reader.onload=()=>resolve(reader.result.split(',')[1]);reader.onerror=()=>reject(new Error('The PDF could not be read. Please select it again.'));reader.readAsDataURL(file);
      });
      payload={pdf_base64:encoded};route+='/pdf';
    }else if(fromWebsite){
      payload={url:values.source_website,cv:priorSource};route+='/website';
    }
    const result=await api(route,'POST',payload);
    if(state?.sandbox && drafts.get(id)?.cv===values.cv){
      const cv=result.cv||'';
      const sourceText=result.source_text||'';
      const source={cv:sourceText,text:[sourceText,result.website?.text].filter(Boolean).join('\n\n')};
      cvSources.set(slot,source);
      drafts.set(id,{...drafts.get(id),cv,...(result.website?{source_website:result.website.url}:{})});
      cvReviews.set(slot,{...result,cv,accepted:[]});
      notice('GPT CV suggestions are ready. Review them before adding them to the identity.');
    }
  }finally{busy.delete(id);render();}
}

root.addEventListener('input', event => {
  if(event.target.id==='graph-timeline'){graphOffset=Number(event.target.value);graphPlaying=false;document.getElementById('graph-position').textContent=`Window end · ${graphOffset} seconds from event start`;return;}
  if (event.target.id === 'resident-search') { query = event.target.value; render(); return; }
  const form = event.target.closest('form');
  if (form && !['auth-form','message-form'].includes(form.id)) {
    const values=Object.fromEntries(new FormData(form));
    for(const input of form.querySelectorAll('input[type="checkbox"]'))values[input.name]=input.checked?'on':'';
    drafts.set(form.id,values);
  }
});

root.addEventListener('change', event => {
  if(event.target.id==='cohort-file'){
    const file=event.target.files[0];if(file)(async()=>{
      if(file.size>5*1024*1024)throw Error('Choose an export below 5 MB.');
      cohortImportDraft={text:await file.text(),format:/\.csv$/i.test(file.name)?'csv':'json',use_memory_context:document.getElementById('legacy-memory-context').checked};
      cohortPreview=await api('/api/cohort/import/preview','POST',cohortImportDraft);render();notice('Import preview ready. Review it before confirming.');
    })().catch(error=>notice(error.message,true));
  }
  if(event.target.id==='legacy-memory-context'){cohortPreview=null;cohortImportDraft=null;}
  if(event.target.id==='onboarding-file'){
    const file=event.target.files[0],slot=agentSlot;
    if(file)(async()=>{
      if(file.size>5*1024*1024)throw new Error('Choose an onboarding export below 5 MB.');
      const bundle=JSON.parse(await file.text());const actor=state.me.id;
      const result=await api('/api/sandbox/onboarding/import','POST',{bundle});
      if(state?.me.id!==actor)return;
      const values=Object.fromEntries(state.sandbox.identity_fields.map(field=>[field.key,result.identity[field.key]||'']));
      drafts.set(`agent-identity-form-${slot}`,{...values,share_values:result.identity.share_values?'on':''});
      onboardingDrafts.set(slot,result);identityReviews.delete(slot);cvReviews.delete(slot);cvEvidence.set(slot,[]);
      if(result.cv_text)cvSources.set(slot,{cv:result.cv_text,text:result.cv_text});else cvSources.delete(slot);
      render();notice('Saved onboarding imported into this draft. Review it, optionally extract CV suggestions with GPT, then submit.');
    })().catch(error=>notice(error.message,true));
  }
  if(event.target.id==='cv-pdf'){
    const file=event.target.files[0],form=event.target.closest('form');
    if(file)extractCv(form,file).catch(error=>notice(error.message,true));
  }
  if(event.target.id==='graph-timeline'){graphOffset=Number(event.target.value);fetchGraph().then(render).catch(error=>notice(error.message,true));}
  if(event.target.id==='agent-slot'){agentSlot=Number(event.target.value);render();}
  if(event.target.id==='graph-window'){graphWindow=Number(event.target.value);fetchGraph().then(render).catch(error=>notice(error.message,true));}
  if (event.target.id === 'memory-source') {
    root.querySelector('.source-preview').textContent = memorySources.find(s=>s.key===event.target.value)?.body || '';
  }
});

root.addEventListener('click', async event => {
  const button = event.target.closest('button'); if (!button) return;
  if (button.dataset.auth) { authMode = button.dataset.auth; render(); }
  if (button.dataset.page) { page = button.dataset.page; await fetchGraph().catch(()=>{}); render();fetchPersonalNotes(); }
  if (button.dataset.connect || button.dataset.peer) {
    peerId = button.dataset.connect || button.dataset.peer; page = 'messages'; render();
  }
  const guarded=['before-sleep','next-day','stop-event','confirm-cohort-import'].includes(button.dataset.action);
  const controlKey='control:'+button.dataset.action;
  if(guarded&&busy.has(controlKey))return;
  if(guarded){busy.add(controlKey);button.disabled=true;}
  try {
    if(button.dataset.memoryDocument){memoryDocument=await api('/api/agent-memory/document?'+new URLSearchParams({agent:button.dataset.memoryDocument}));render();root.querySelector('.memory-document')?.scrollIntoView({block:'center'});}
    if(button.dataset.action==='confirm-cohort-import'){await api('/api/cohort/import/confirm','POST',{import:cohortImportDraft,preview_hash:cohortPreview.preview_hash,confirmed:true});cohortImportDraft=null;cohortPreview=null;await refresh();notice('Reviewed cohort imported. The event remains idle until Start.');}
    if(button.dataset.action==='close-memory'){memoryDocument=null;render();}
    if(button.dataset.action==='download-memory'&&memoryDocument){
      const url=URL.createObjectURL(new Blob([memoryDocument.markdown],{type:'text/markdown;charset=utf-8'}));
      const link=document.createElement('a');link.href=url;link.download='MEMORY.md';link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
    }
    if(button.dataset.action==='identity-discard-review'){
      const slot=Number(button.dataset.slot);identityReviews.delete(slot);drafts.delete(`identity-review-form-${slot}`);render();
    }
    if(button.dataset.action==='identity-back'){
      const slot=Number(button.dataset.slot),form=button.closest('form'),id=form.id;
      if(busy.has(id))return;
      busy.add(id);
      try{
        const result=await api('/api/sandbox/identity/review','POST',{markdown:form.elements.markdown.value,cv_evidence:identityReviews.get(slot).identity.cv_evidence||[]});
        const values=Object.fromEntries(state.sandbox.identity_fields.map(field=>[field.key,result.identity[field.key]||'']));
        drafts.set(`agent-identity-form-${slot}`,{...values,share_values:result.identity.share_values?'on':''});
        cvEvidence.set(slot,result.identity.cv_evidence||[]);cvReviews.delete(slot);identityReviews.delete(slot);drafts.delete(id);
      }finally{busy.delete(id);render();}
    }
    if(button.dataset.action==='extract-cv'){
      await extractCv(button.closest('form'));
    }
    if(button.dataset.action==='extract-website')await extractCv(button.closest('form'),null,true);
    if(button.dataset.cvAccept!==undefined){
      const form=button.closest('form'),slot=Number(form.dataset.agentSlot),review=cvReviews.get(slot);
      const index=Number(button.dataset.cvAccept),item=review?.suggestions[index];
      if(!item||review.accepted.includes(index))return;
      let target=form.elements.namedItem(item.field);
      let updated=target.value.includes(item.text)?target.value:[target.value,item.text].filter(Boolean).join('\n');
      if(updated.length>target.maxLength && item.field!=='cv_notes'){
        target=form.elements.namedItem('cv_notes');updated=[target.value,item.text].filter(Boolean).join('\n');
      }
      if(updated.length>target.maxLength)throw new Error('This field is full. Edit it before adding the suggestion.');
      target.value=updated;target.dispatchEvent(new Event('input',{bubbles:true}));
      cvEvidence.set(slot,[...(cvEvidence.get(slot)||[]),{...item,field:target.name}]);review.accepted.push(index);render();
    }
    if(button.dataset.action==='export-identity'){
      const result=await api('/api/sandbox/identity?slot='+button.dataset.slot);
      const url=URL.createObjectURL(new Blob([result.markdown],{type:'text/markdown;charset=utf-8'}));
      const link=document.createElement('a');link.href=url;link.download=result.filename;link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
    }
    if(button.dataset.action==='before-sleep'){await api('/api/day-cycle/sleep','POST',{});await refresh();}
    if(button.dataset.action==='next-day'){await api('/api/day-cycle/next','POST',{});await refresh();}
    if(button.dataset.action==='graph-live'){graphOffset=null;graphPlaying=false;await fetchGraph();render();}
    if(button.dataset.action==='graph-play'){graphPlaying=!graphPlaying;if(graphPlaying&&graphOffset===null)graphOffset=0;await fetchGraph();render();}
    if(button.dataset.action==='stop-event'){
      await api('/api/event/stop','POST',{}); await refresh(); notice('Stop requested. Pending model replies will not be delivered.');
    }
    if(button.dataset.eventConversation){conversationId=button.dataset.eventConversation;page='conversations';render();}
    if (button.dataset.startConversation) {
      const result=await api('/api/conversations/actions','POST',{start_conversations:[{with:button.dataset.startConversation}]});
      conversationId=result.created_conversations[0]; page='conversations'; await refresh();
    }
    if (button.dataset.openConversation) { conversationId=button.dataset.openConversation; render(); }
    if (button.dataset.joinConversation || button.dataset.leaveConversation) {
      conversationId=button.dataset.joinConversation || button.dataset.leaveConversation;
      await api('/api/conversations/actions','POST',button.dataset.joinConversation?{join_conversations:[conversationId]}:{leave_conversations:[conversationId]});
      await refresh();
    }
    if (button.id === 'refresh') { await refresh(); notice('Residency updated.'); }
    if (button.id === 'check-hermes') await checkHermes();
    if (button.dataset.action === 'logout') {
      agentAccountsData=null;memoryDocument=null;cohortImportDraft=null;cohortPreview=null;
      await api('/api/logout','POST',{}); state = null; csrf = ''; drafts.clear(); cvReviews.clear(); cvEvidence.clear(); identityReviews.clear();cvSources.clear();onboardingDrafts.clear();personalNotesData=null;personalNotesAt=0;semanticResults=[]; memorySources=[]; memoryResults=null; memoryQuery=''; conversationId=''; page='residents'; render();
    }
    if (button.dataset.action === 'memory-all') { memoryResults=null; memoryQuery=''; drafts.delete('memory-search-form'); render(); }
    if (button.dataset.action === 'memory-sources') { memorySources=(await api('/api/memory/sources')).sources; render(); root.querySelector('#memory-note-form')?.closest('details')?.setAttribute('open',''); }
    if (button.dataset.memoryPin || button.dataset.memoryHide) {
      const id = button.dataset.memoryPin || button.dataset.memoryHide;
      await api(`/api/memory/notes/${id}`,'PATCH',button.dataset.memoryHide?{hidden:true}:{pinned:button.dataset.pinned==='true'});
      await refresh();
    }
    if (button.dataset.resolve) {
      await api(`/api/problems/${button.dataset.resolve}`,'PATCH',{status:button.dataset.status}); await refresh();
    }
  } catch (error) { notice(error.message,true); } finally {if(guarded){busy.delete(controlKey);if(button.isConnected)button.disabled=false;}}
});

root.addEventListener('submit', async event => {
  event.preventDefault(); const form = event.target; const id = form.id;
  if (busy.has(id)) return;
  const data = Object.fromEntries(new FormData(form));
  const sendingTo = peerId;
  busy.add(id); for (const button of form.querySelectorAll('button')) button.disabled = true;
  try {
    if (id === 'auth-form') {
      const result = await api(authMode==='join'?'/api/join':'/api/login','POST',data);
      memorySources=[]; memoryResults=null; memoryQuery=''; conversationId='';
      csrf = result.csrf; await refresh(); checkHermes();
      if(state.sandbox){page='agentSetup';render();}
    } else if(form.dataset.memoryContextOwner){
      await api('/api/agent-memory/policy','POST',{owner_id:form.dataset.memoryContextOwner,network_context:form.elements.network_context.checked});await refresh();notice('Memory context choice saved for later turns.');
    } else if(form.dataset.identityReviewSlot){
      const slot=Number(form.dataset.identityReviewSlot),review=identityReviews.get(slot);
      await api('/api/sandbox/identity/submit','POST',{slot,markdown:data.markdown,cv_evidence:review.identity.cv_evidence||[],...(data.limit_usd!==undefined?{budget:{limit_usd:data.limit_usd,reserve_usd:data.reserve_usd}}:{}),...(onboardingDrafts.has(slot)?{memory_policy:onboardingDrafts.get(slot).memory_policy}:{})});
      onboardingDrafts.delete(slot);
      drafts.delete(id);drafts.delete(`agent-identity-form-${slot}`);identityReviews.delete(slot);cvEvidence.delete(slot);cvReviews.delete(slot);
      await refresh();notice(`Agent ${slot} submitted. Your reviewed identity is saved.`);
    } else if(form.dataset.walletOwner){
      await api('/api/agent-budget','POST',{owner_id:form.dataset.walletOwner,...data});drafts.delete(id);await refresh();notice('USD allowance saved. Networking starts only when you press Start.');
    } else if(form.dataset.requestOwner){
      await api('/api/agent-requests','POST',{owner_id:form.dataset.requestOwner,...data});drafts.delete(id);await refresh();notice('Your agent will consider this private request on its next funded turn.');
    } else if(form.dataset.agentSlot){
      const slot=Number(form.dataset.agentSlot);
      const result=await api('/api/sandbox/identity/review','POST',{identity:identityDraft(data,slot)});
      identityReviews.set(slot,result);drafts.delete(`identity-review-form-${slot}`);
      notice('Review and edit IDENTITY.md, then submit when ready. Nothing has been saved yet.');
    } else if(id==='compass-observation-form'){
      await api('/api/sandbox/compass','POST',data);drafts.delete(id);await refresh();notice('Evidence-linked observation saved. The starting identity is preserved.');
    } else if(id==='semantic-memory-form'){
      semanticResults=(await api('/api/agent-memory?'+new URLSearchParams(data))).results;render();
    } else if (id === 'profile-form') {
      await api('/api/profile','PATCH',data); drafts.delete(id); await refresh(); notice('Your profile is saved.');
    } else if (id === 'introduction-form') {
      await api('/api/introductions','POST',data); drafts.delete(id); await refresh(); notice('Your introduction is on the board.');
    } else if(id==='host-event-form'){
      await api('/api/event/start','POST',{max_calls:state.sandbox?.live_cohort?null:Number(data.max_calls),...(state.event.npc?{npc_enabled:data.npc_enabled==='on'}:{}),...(state.cycle?{seven_days:data.seven_days==='on'}:{})});drafts.delete(id);semanticResults=[];page='conversations';showIntroductions=true;await refresh();notice('Event started. Personas will choose what to discuss.');
    } else if (id === 'conversation-start-form') {
      const result=await api('/api/conversations/actions','POST',{start_conversations:[{with:data.with}]});
      conversationId=result.created_conversations[0]; drafts.delete(id); await refresh();
    } else if (id.startsWith('conversation-message-') && form.dataset.conversation) {
      await api('/api/conversations/actions','POST',{messages:[{conversation_id:form.dataset.conversation,body:data.body}]});
      drafts.delete(id); await refresh();
    } else if (id === 'problem-form') {
      await api('/api/problems','POST',data); drafts.delete(id); await refresh(); notice('Your problem is on the board.');
    } else if (form.dataset.problem) {
      await api(`/api/problems/${form.dataset.problem}/comments`,'POST',data); drafts.delete(id); await refresh();
    } else if (id === 'message-form') {
      await api('/api/messages','POST',{...data,recipient_id:sendingTo}); await refresh();
    } else if (id === 'assistant-form') {
      const work = api('/api/assistant','POST',data);
      // Fetch the durable pending turn without waiting for inference to finish.
      setTimeout(() => { if (state) refresh().catch(()=>{}); },400);
      await work; drafts.delete(id); await refresh();
    } else if (id === 'memory-policy-form') {
      const phrases = value => value.split(/[,\n]/).map(v=>v.trim()).filter(Boolean);
      await api('/api/memory/policy','PATCH',{
        instructions:data.instructions, topics:phrases(data.topics), exclude_terms:phrases(data.exclude_terms),
        weights:Object.fromEntries(state.memory.categories.map(c=>[c,Number(data[`weight_${c}`])])),
        minimum_importance:Number(data.minimum_importance), auto_after:Number(data.auto_after),
        auto_extract:data.auto_extract==='true', recall_enabled:data.recall_enabled==='true',
        capture_conversations:data.capture_conversations==='true'
      }); drafts.delete(id); await refresh(); notice('Memory priorities saved.');
    } else if (id === 'memory-extract-form') {
      const result = await api('/api/memory/extract','POST',{});
      await refresh(); notice(`${result.stored_units} notes selected locally. No model call was made.`);
    } else if (id === 'memory-search-form') {
      memoryQuery=data.q; memoryResults=(await api('/api/memory?' + new URLSearchParams(data))).results; render();
    } else if (id === 'memory-note-form') {
      await api('/api/memory/notes','POST',data); drafts.delete(id); memorySources=[]; await refresh(); notice('Selected note saved.');
    }
  } catch (error) {
    notice(error.message,true);
    if (id === 'assistant-form' && state) await refresh().catch(()=>{});
  } finally {
    busy.delete(id);
    if (state) render();
    else for (const button of root.querySelectorAll('form button')) button.disabled=false;
  }
});

setInterval(() => {
  const typing = ['INPUT','TEXTAREA','SELECT'].includes(document.activeElement?.tagName);
  if (state && !typing && busy.size===0 && !['profile','memory','hostEvent','agentSetup','conversations'].includes(page)) refresh().catch(error=>notice(error.message,true));
},8000);

setInterval(()=>{
  const typing=['INPUT','TEXTAREA','SELECT'].includes(document.activeElement?.tagName);
  if(state && ['hostEvent','conversations','myAgents'].includes(page) && !typing && busy.size===0 && !graphPlaying)refresh().catch(error=>notice(error.message,true));
},2000);

setInterval(()=>{
  if(!state||!graphPlaying||!['conversations','hostEvent'].includes(page)||busy.size)return;
  graphOffset=(graphOffset||0)+Math.max(1,Math.ceil((graphData?.duration||1)/60));
  if(graphOffset>=(graphData?.duration||1)){graphOffset=Math.ceil(graphData?.duration||1);graphPlaying=false;}
  fetchGraph().then(render).catch(error=>{graphPlaying=false;notice(error.message,true);});
},1000);

api('/api/setup').catch(()=>({identity_test:false})).then(value=>{setup=value;if(setup.identity_test&&!setup.host_signup_available)authMode='login';return refresh();}).then(checkHermes).catch(error=>{ render(); if (error.message!=='Please sign in') notice(error.message,true); });
