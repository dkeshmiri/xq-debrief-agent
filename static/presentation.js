const $ = id => document.getElementById(id);
let frame = null, joined = false, busy = false, state = {}, online = false, scriptLoaded = false;
let scriptRevision = null, visualKey = null, previewIndex = 0;
let showcase = false;
function setShowcase(enabled) {
    showcase = enabled;
    $('presentation-layout').classList.toggle('showcase', enabled);
    $('showcase-toggle').setAttribute('aria-pressed', String(enabled));
    $('showcase-toggle').textContent = enabled ? 'Return to split view' : 'Showcase view';
}
$('showcase-toggle').addEventListener('click', () => setShowcase(!showcase));
window.addEventListener('keydown', event => { if (event.key === 'Escape') setShowcase(false); });
function notice(message = '') { $('notice').textContent = message; $('notice').hidden = !message; }
async function api(action, method = 'POST') {
    const response = await fetch('/api/presentation/' + action, {method, cache:'no-store',
        ...(method === 'GET' ? {signal:AbortSignal.timeout(5000)} : {})});
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || 'The presentation service could not be reached.');
    return data;
}
function controls() {
    $('preview-chapter').disabled = busy || state.active || state.busy;
    $('profile-upload').disabled = busy || state.active || state.busy;
    $('reset-source').disabled = busy || state.active || state.busy;
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
    if (frame?.setReplicaIds) frame.setReplicaIds(data.replica_participant_ids || []);
    if (scriptRevision !== data.revision) {
        scriptLoaded = false; visualKey = null; scriptRevision = data.revision; previewIndex = 0;
        $('chapters').replaceChildren(); $('full-script').replaceChildren();
        $('preview-chapter').replaceChildren();
    }
    if (!scriptLoaded) {
        for (const chapter of data.chapters) {
            const option = document.createElement('option'); option.value = $('preview-chapter').children.length;
            option.textContent = chapter.title; $('preview-chapter').appendChild(option);
            const li = document.createElement('li'); li.textContent = chapter.title; $('chapters').appendChild(li);
            const h = document.createElement('h3'); h.textContent = chapter.title;
            const p = document.createElement('p'); p.textContent = chapter.text; $('full-script').append(h,p);
        }
        scriptLoaded = true;
    }
    const displayIndex = data.active ? data.index : previewIndex;
    $('preview-chapter').value = String(displayIndex);
    [...$('chapters').children].forEach((li,i) => i === displayIndex ? li.setAttribute('aria-current','step') : li.removeAttribute('aria-current'));
    $('chapter-title').textContent = data.chapters[displayIndex].title;
    $('script').textContent = data.chapters[displayIndex].text;
    $('visual-source').textContent = data.source;
    const key = data.chapters[displayIndex].visual;
    if (visualKey !== `${data.revision}:${displayIndex}`) {
        renderVisual(data.visuals?.[key]);
        visualKey = `${data.revision}:${displayIndex}`;
    }
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
$('preview-chapter').addEventListener('change', () => {
    previewIndex = Number($('preview-chapter').value); render(state);
});
function renderVisual(chart) {
    const container = $('chapter-visual'); container.replaceChildren();
    container.dataset.kind = chart?.kind || 'overview';
    function node(tag, text, className) {
        const el = document.createElement(tag); el.textContent = text;
        if (className) el.className = className;
        return el;
    }
    if (!chart) { container.append(node('p', 'No chart is assigned to this chapter.')); return; }
    container.append(node('h2', chart.title), node('p', chart.note, 'chart-note'));
    if (chart.kind === 'disc') {
        const plots = node('div', '', 'disc-plots');
        for (const profile of chart.profiles) {
            const plot = node('section', '', 'disc-plot');
            plot.append(node('h3', profile.label));
            const grid = node('div', '', 'disc-grid');
            const axis = node('div', '', 'disc-axis');
            for (const tick of ['100', '75', '50', '25', '0']) axis.append(node('span', tick));
            grid.append(axis);
            for (const score of profile.scores) {
                const column = node('div', '', 'disc-column');
                const known = typeof score.value === 'number' && Number.isFinite(score.value);
                column.dataset.focus = String(chart.focus.includes(score.key));
                column.setAttribute('aria-label', `${profile.label} ${score.label}: ${known ? score.value : 'Not reported'}`);
                column.append(node('strong', known ? String(score.value) : '—', 'disc-value'));
                const well = node('div', '', 'disc-well');
                const bar = node('div', '', 'score-bar'); bar.dataset.color = score.key;
                bar.style.height = known ? `${Math.max(0, Math.min(100, score.value))}%` : '0%';
                if (profile.label === 'Adapted') bar.classList.add('adapted');
                well.append(bar); column.append(well, node('span', score.key)); grid.append(column);
            }
            plot.append(grid); plots.append(plot);
        }
        container.append(plots, node('p', 'D · Dominance   I · Influence   S · Steadiness   C · Compliance. A dash means not reported.', 'chart-note'));
        return;
    }
    for (const card of chart.cards || []) {
        const el = node('div', '', 'perspective-card');
        el.append(node('h3', card.title), node('p', card.text)); container.append(el);
    }
    if (chart.rows) {
        const scale = node('div', '', 'chart-scale');
        for (const tick of ['0', '50', '100']) scale.append(node('span', tick));
        container.append(scale);
    }
    const composites = node('div', '', 'eq-composites');
    for (const row of chart.rows || []) {
        if (row.composite) {
            const value = row.series[0].value;
            const tile = node('div', '', 'eq-composite');
            tile.dataset.color = row.label === 'Self composite' ? 'self' : row.label === 'Others composite' ? 'others' : 'total';
            tile.append(node('span', row.label), node('strong', value == null ? 'Not reported' : String(value)));
            composites.append(tile); continue;
        }
        const group = node('div', '', 'score-group'); group.append(node('h3', row.label));
        for (const series of row.series) {
            const line = node('div', '', 'score-line');
            const known = typeof series.value === 'number' && Number.isFinite(series.value);
            line.append(node('span', series.label), node('strong', known ? String(series.value) : 'Not reported'));
            const track = node('div', '', 'score-track');
            track.setAttribute('aria-hidden', 'true');
            if (known) {
                const bar = node('div', '', 'score-bar');
                bar.dataset.color = series.color;
                bar.style.width = `${Math.max(0, Math.min(100, series.value))}%`;
                if (series.label === 'Adapted') bar.classList.add('adapted');
                track.append(bar);
            } else track.classList.add('missing');
            line.append(track); group.append(line);
        }
        container.append(group);
    }
    if (composites.children.length) {
        container.append(node('h3', 'Reported composites', 'composite-title'), composites);
    }
}
async function changeSource(profile) {
    const response = await fetch('/api/presentation/source', {
        method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({profile})
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || 'Could not load this profile.');
}
$('profile-upload').addEventListener('change', () => run(async () => {
    const file = $('profile-upload').files[0];
    if (!file) return;
    try {
        if (file.size > 950000) throw new Error('Choose a profile JSON smaller than 950 KB.');
        await changeSource(JSON.parse(await file.text()));
    } finally { $('profile-upload').value = ''; }
}));
$('reset-source').addEventListener('click', () => run(() => changeSource(null)));
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
    frame = new window.PresentationPlayer($('video-container'), $('placeholder'), notice);
    frame.on('error', () => { joined=false; controls(); notice('Video connection failed. End the presentation before retrying.'); });
    frame.on('left-meeting', () => { joined=false; controls(); });
    const c = data.conversation;
    await frame.join({url:c.conversation_url, startVideoOff:true, startAudioOff:true, userName:'XQ Presentation Viewer', ...(c.meeting_token ? {token:c.meeting_token} : {})});
    joined = true;
    await waitForPresenter();
    await api('play');
}
async function waitForPresenter() {
    // Room join can precede the replica. Require its video and backend presence,
    // then allow a short warm-up before the first Echo. Never resend blindly.
    const deadline = Date.now() + 45000;
    let readySince = null;
    do {
        await refresh();
        if (state.shutdown_reason || !state.active)
            throw new Error('The presentation ended before speech could begin. End this session and try again.');
        const ready = online && joined && state.connected
            && state.replica_participant_ids?.length > 0
            && !!frame?.video?.srcObject;
        if (ready) {
            if (readySince === null) readySince = Date.now();
            $('status').textContent = 'Presenter connected. Preparing speech…';
            if (Date.now() - readySince >= 5000) return;
        } else {
            readySince = null;
            $('status').textContent = 'Waiting for the presenter to be ready…';
        }
        await new Promise(resolve=>setTimeout(resolve,300));
    } while (Date.now()<deadline);
    throw new Error('The presenter did not become ready. End this presentation and try again.');
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
