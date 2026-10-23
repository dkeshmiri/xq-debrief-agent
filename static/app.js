const $ = id => document.getElementById(id);
const workspaceBase = document.body?.dataset?.apiBase || '';
const businessWorkspace = document.body?.dataset?.experience === 'business';
let callFrame = null, conversationId = null, busy = false, online = false, joined = false;
let activity = {}, lastCode = '', keepalive = null, lastInput = 0, profiles = [];
const sections = [...document.querySelectorAll('[data-section]')];

function notice(message = '') {
    $('notice').textContent = message;
    $('notice').hidden = !message;
}
async function request(url, body, method = 'POST') {
    const response = await fetch(workspaceBase + url, {
        method, headers: {'Content-Type': 'application/json'},
        ...(body === undefined ? {} : {body: JSON.stringify(body)}),
        ...(method === 'GET' ? {signal: AbortSignal.timeout(5000), cache: 'no-store'} : {})
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || `Request failed (${response.status}). Please try again.`);
    return data;
}
function controls() {
    const active = activity.active || !!conversationId;
    const ready = online && activity.connected && active && joined && !busy && !activity.changing;
    $('start-button').disabled = !online || busy || active || activity.changing || !$('person-select').value;
    $('start-button').hidden = active;
    $('end-button').hidden = !active;
    $('end-button').disabled = busy;
    $('person-select').disabled = busy || active || activity.changing;
    for (const id of ['speak-button', 'next-button', 'repeat-button', 'restart-button'])
        $(id).disabled = !ready || activity.pending || activity.question_ready || activity.code === 'reasoning';
    $('ask-button').disabled = !ready || activity.answer_pending || activity.code === 'reasoning' || !$('question-input').value.trim();
    $('dismiss-button').disabled = !ready || !activity.question_ready || activity.pending;
    $('pause-question-button').disabled = !ready || activity.phase !== 'narrating'
        || activity.code !== 'speaking' || !!activity.interrupted;
    const questionHint = activity.interrupted
        ? 'Pausing narration. Waiting for the guide to stop…'
        : activity.question_ready
            ? 'Question mode is open. Speak or type below, or continue without a question.'
            : 'Pause the guide manually to ask by voice or type below.';
    if ($('question-mode-hint').textContent !== questionHint)
        $('question-mode-hint').textContent = questionHint;
    $('session-label').textContent = active ? 'Conversation open' : 'Your private conversation space';
}
function renderActivity(data) {
    activity = data;
    const currentProfile = profiles.find(person => person.person_id === data.person_id);
    if (data.active && currentProfile) {
        $('person-select').value = currentProfile.file;
        $('profile-initial').textContent = currentProfile.display_name.charAt(0);
    }
    if (data.active && !callFrame && !busy)
        notice('A session is already open. End it here before beginning a new conversation.');
    $('feed-label').textContent = 'Live activity';
    $('activity-current').dataset.code = data.code;
    $('status').textContent = data.title;
    $('activity-detail').textContent = data.detail;
    if (data.code !== lastCode) {
        const item = document.createElement('li');
        item.textContent = `${new Date().toLocaleTimeString([], {hour: '2-digit', minute: '2-digit'})} · ${data.title}`;
        $('activity-history').prepend(item);
        while ($('activity-history').children.length > 4) $('activity-history').lastElementChild.remove();
        lastCode = data.code;
    }
    const index = data.state === 'complete' ? sections.length : sections.findIndex(el => el.dataset.section === data.state);
    sections.forEach((el, i) => {
        el.classList.toggle('active', i === index);
        el.classList.toggle('done', i < index);
        if (i === index) el.setAttribute('aria-current', 'step');
        else el.removeAttribute('aria-current');
    });
    const label = sections[index]?.querySelector('strong').textContent || (data.state === 'complete' ? 'Conversation complete' : 'Welcome');
    $('section-label').textContent = label;
    $('stage-section').textContent = label;
    controls();
}
async function refresh() {
    try {
        const data = await request('/api/activity', undefined, 'GET');
        online = true;
        renderActivity(data);
    } catch {
        online = false;
        $('feed-label').textContent = 'Updates unavailable';
        $('activity-current').dataset.code = 'offline';
        $('status').textContent = 'Cannot reach the app';
        $('activity-detail').textContent = 'Live updates are paused. Reconnecting automatically; the last observed activity remains below.';
        controls();
    }
}
async function poll() {
    await refresh();
    setTimeout(poll, document.hidden ? 5000 : 1000);
}
async function run(action) {
    if (busy) return;
    busy = true;
    notice();
    controls();
    try { await action(); }
    catch (error) { notice(error.message); }
    finally { busy = false; await refresh(); controls(); }
}
async function startSession() {
    if (!window.DailyIframe) throw new Error('The video player could not load. Check your connection and reload the page.');
    await request('/api/person/select', {file: $('person-select').value});
    const data = await request('/api/session/start');
    conversationId = data.conversation.conversation_id;
    controls();
    callFrame = window.DailyIframe.createFrame($('video-container'), {
        showLeaveButton: false, iframeStyle: {width: '100%', height: '100%', border: '0'}
    });
    callFrame.on('error', () => {
        joined = false;
        controls();
        notice('The video connection encountered an error. End the conversation and try again.');
    });
    callFrame.on('left-meeting', () => {
        joined = false;
        controls();
        $('video-placeholder').hidden = false;
        notice('The video room has disconnected. End the session before starting again.');
    });
    await callFrame.join({
        url: data.conversation.conversation_url, userName: data.voice_user_name,
        startVideoOff: true, startAudioOff: true,
        ...(data.conversation.meeting_token ? {token: data.conversation.meeting_token} : {})
    });
    joined = true;
    $('video-placeholder').hidden = true;
    await request('/api/debrief/tracked/next');
}
async function endSession() {
    await request('/api/session/end');
    joined = false;
    conversationId = null;
    stopKeepalive();
    if (callFrame) {
        await callFrame.destroy();
        callFrame = null;
    }
    $('video-placeholder').hidden = false;
    $('answer-card').hidden = true;
    notice();
}
async function askQuestion() {
    const question = $('question-input').value.trim();
    if (!question) return;
    const current = await request('/api/activity', undefined, 'GET');
    if (current.phase === 'narrating' && current.pending) {
        await pauseForQuestion();
    }
    const data = await request('/api/question', {question});
    $('answer-text').textContent = data.answer || 'Your question has been received.';
    $('answer-card').hidden = false;
    $('question-input').value = '';
    stopKeepalive();
}
async function pauseForQuestion() {
    await request('/api/debrief/interrupt');
    $('question-mode-hint').textContent = 'Pausing narration. Waiting for the guide to stop…';
    const deadline = Date.now() + 10000;
    while (true) {
        const status = await request('/api/activity', undefined, 'GET');
        renderActivity(status);
        if (status.question_ready && !status.interrupted) return;
        if (!status.active || !status.connected)
            throw new Error('The conversation disconnected before question mode opened.');
        if (Date.now() >= deadline)
            throw new Error('Speech has not stopped yet. Wait for question mode to open before asking.');
        await new Promise(resolve => setTimeout(resolve, 150));
    }
}
async function enterManualQuestionMode() {
    await pauseForQuestion();
    $('question-input').focus();
}
function stopKeepalive() { clearInterval(keepalive); keepalive = null; }
async function keepQuestionOpen() {
    if (Date.now() - lastInput > 15000) return stopKeepalive();
    if (!activity.question_ready) return;
    try { await request('/api/question/keepalive'); } catch { /* The status poll reports connection loss. */ }
}
$('question-input').addEventListener('input', () => {
    lastInput = Date.now();
    controls();
    if (keepalive === null) {
        keepQuestionOpen();
        keepalive = setInterval(keepQuestionOpen, 5000);
    }
});
$('question-input').addEventListener('blur', stopKeepalive);
$('person-select').addEventListener('change', () => {
    $('profile-initial').textContent = $('person-select').selectedOptions[0]?.textContent.charAt(0) || 'X';
    controls();
});
for (const [id, action] of Object.entries({
    'start-button': startSession, 'end-button': endSession, 'ask-button': askQuestion,
    'pause-question-button': enterManualQuestionMode,
    'dismiss-button': async () => { await request('/api/question/dismiss'); stopKeepalive(); }
})) $(id).addEventListener('click', () => run(action));
for (const [id, route] of Object.entries({
    'speak-button': 'speak', 'next-button': 'next', 'repeat-button': 'repeat', 'restart-button': 'restart'
})) $(id).addEventListener('click', () => run(async () => {
    const data = await request(`/api/debrief/${route}`);
    $('output').textContent = data.spoken || data.message || 'Conversation updated.';
}));
document.querySelectorAll('.app-nav, .switch-profile').forEach(link => link.addEventListener('click', event => {
    if (activity.active || conversationId || busy) {
        event.preventDefault();
        notice('End the current conversation before switching profiles or uploading reports.');
    }
}));
window.addEventListener('beforeunload', event => {
    if (activity.active || conversationId) { event.preventDefault(); event.returnValue = ''; }
});
async function loadPersonas() {
    try {
        const data = await request('/api/personas', undefined, 'GET');
        profiles = data.personas;
        $('person-select').replaceChildren();
        for (const person of data.personas) {
            const option = document.createElement('option');
            option.value = person.file;
            option.textContent = person.family_role ? `${person.display_name} — ${person.family_role}` : person.display_name;
            $('person-select').appendChild(option);
        }
        const file = new URLSearchParams(window.location.search).get('file');
        if (data.personas.some(person => person.file === file)) $('person-select').value = file;
        $('person-select').dispatchEvent(new Event('change'));
        if (!data.personas.length) notice(businessWorkspace ? 'Import a workplace assessment profile to begin.' : 'Create a family profile to begin.');
    } catch (error) { notice(error.message); }
}
loadPersonas();
poll();
