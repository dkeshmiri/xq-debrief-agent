const $ = id => document.getElementById(id);
let frame = null, joined = false, busy = false, state = {}, online = false, scriptLoaded = false;
function notice(message = '') { $('notice').textContent = message; $('notice').hidden = !message; }
async function api(action, method = 'POST') {
    const response = await fetch('/api/presentation/' + action, {method, cache:'no-store',
        ...(method === 'GET' ? {signal:AbortSignal.timeout(5000)} : {})});
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || 'The presentation service could not be reached.');
    return data;
}
function controls() {
    $('start').hidden = state.active;
    $('start').disabled = !online || busy || state.active || state.busy;
    $('end').hidden = !state.active && !frame;
    $('end').disabled = busy || state.busy;
    const ready = online && joined && state.active && state.connected && !state.shutdown_reason && state.remaining_seconds > 0 && !busy && !state.busy && !state.pending;
    $('play').disabled = !ready;
    $('repeat').disabled = !ready;
    $('next').disabled = !ready || !state.completed || state.index >= state.chapters.length-1;
}
function render(data) {
    state = data; online = true;
    if (!scriptLoaded) {
        for (const chapter of data.chapters) {
            const li = document.createElement('li'); li.textContent = chapter.title; $('chapters').appendChild(li);
            const h = document.createElement('h3'); h.textContent = chapter.title;
            const p = document.createElement('p'); p.textContent = chapter.text; $('full-script').append(h,p);
        }
        scriptLoaded = true;
    }
    [...$('chapters').children].forEach((li,i) => i === data.index ? li.setAttribute('aria-current','step') : li.removeAttribute('aria-current'));
    $('chapter-title').textContent = data.chapters[data.index].title;
    $('script').textContent = data.chapters[data.index].text;
    $('runtime').textContent = data.word_count + ' words · approximately ' + Math.ceil(data.word_count/150) + '–' + Math.ceil(data.word_count/110) + ' minutes of speech';
    $('budget').textContent = data.active ? Math.floor(data.remaining_seconds/60) + ':' + String(data.remaining_seconds%60).padStart(2,'0') + ' remaining in session budget' : '15-minute session budget';
    $('status').textContent = data.shutdown_reason === 'max_call_duration' || (data.active && !data.remaining_seconds) ? 'Session time limit reached. End this session before starting again.' :
        data.shutdown_reason ? 'The provider ended the presentation. End this session before starting again.' :
        data.busy ? 'Updating the presentation connection…' :
        !data.active ? 'Ready for your presentation.' :
        !data.connected ? 'Waiting for the video connection. If it does not return, end the session.' :
        !joined ? 'This page has not joined the existing session. End it before starting again.' :
        data.speaking ? 'Presenting: ' + data.chapters[data.index].title :
        data.pending ? 'Script submitted. Waiting for speech to begin.' :
        data.completed ? 'Chapter complete.' : 'Connected and ready to present.';
    controls();
}
async function refresh() {
    try { render(await api('status','GET')); }
    catch { online = false; $('status').textContent = 'Live updates unavailable. Reconnecting…'; controls(); }
}
async function run(action) {
    if (busy) return;
    busy = true; notice(); controls();
    try { await action(); } catch (error) { notice(error.message); }
    finally { busy = false; await refresh(); }
}
async function end() {
    await api('end');
    joined = false;
    if (frame) { await frame.destroy(); frame = null; }
    $('placeholder').hidden = false;
}
async function start() {
    if (!window.DailyIframe) throw new Error('Video player unavailable. Check your internet connection and reload.');
    const data = await api('start');
    await refresh();
    frame = window.DailyIframe.createFrame($('video-container'), {showLeaveButton:false, iframeStyle:{width:'100%',height:'100%',border:'0'}});
    frame.on('error', () => { joined=false; controls(); notice('Video connection failed. End the presentation before retrying.'); });
    frame.on('left-meeting', () => { joined=false; controls(); });
    const c = data.conversation;
    await frame.join({url:c.conversation_url, startVideoOff:true, startAudioOff:true, userName:'XQ Presentation Viewer', ...(c.meeting_token ? {token:c.meeting_token} : {})});
    joined = true; $('placeholder').hidden = true;
    const deadline = Date.now()+20000;
    do {
        await refresh();
        if (state.connected) { await api('play'); return; }
        if (state.shutdown_reason) break;
        await new Promise(resolve=>setTimeout(resolve,300));
    } while (Date.now()<deadline);
    throw new Error('The guide could not connect. End this presentation and try again.');
}
for (const [id, action] of Object.entries({start, end, play:()=>api('play'), next:()=>api('next'), repeat:()=>api('repeat')}))
    $(id).addEventListener('click',()=>run(action));
document.querySelectorAll('a[href="/"]').forEach(link=>link.addEventListener('click',event=>{
    if (busy || state.active) { event.preventDefault(); notice('End the presentation before leaving this page.'); }
}));
window.addEventListener('beforeunload',event=>{if(state.active){event.preventDefault();event.returnValue='';}});
async function poll() {
    await refresh();
    if (online && joined && !busy && !state.busy && !state.shutdown_reason && state.connected && state.completed && !state.pending && $('autoplay').checked) {
        if (state.index < state.chapters.length-1) await run(()=>api('next'));
        else { await run(end); if (!state.active) notice('Presentation complete. Thank you.'); }
    }
    setTimeout(poll,1000);
}
poll();
