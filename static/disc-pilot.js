'use strict';
(() => {
  const $ = id => document.getElementById(id);
  const base = $('main').dataset.base;
  const storageKey = 'xq-disc-frequency-pilot';
  const contexts = ['natural', 'adapted'];
  let bank, report, page = 0, responses = {natural: {}, adapted: {}};
  let controller, audioUrl, generation = 0;

  function notice(message = '') {
    $('notice').textContent = message;
    $('notice').hidden = !message;
  }
  function show(id) {
    ['welcome', 'assessment', 'report'].forEach(view => $(view).hidden = view !== id);
  }
  function submission() { return {version: bank.version, responses}; }
  function save() {
    try { sessionStorage.setItem(storageKey, JSON.stringify({...submission(), page})); }
    catch { notice('Progress could not be saved in this tab. You can continue and download your completed report.'); }
  }
  function restore() {
    try {
      const saved = JSON.parse(sessionStorage.getItem(storageKey));
      if (!saved || saved.version !== bank.version || !Number.isInteger(saved.page) || saved.page < 0 || saved.page >= 8) return false;
      const ids = new Set(bank.items.map(item => item.id));
      if (!saved.responses || Object.keys(saved.responses).length !== 2) return false;
      if (!contexts.every(context => {
        const answers = saved.responses[context];
        return answers && typeof answers === 'object' && !Array.isArray(answers) &&
          Object.entries(answers).every(([id, value]) => ids.has(id) && Number.isInteger(value) && value >= 0 && value <= 4);
      })) return false;
      responses = saved.responses;
      page = saved.page;
      return true;
    } catch { return false; }
  }
  async function request(path, body, signal) {
    const response = await fetch(base + path, body ? {
      method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body), signal,
    } : {signal});
    if (!response.ok) {
      const error = await response.json().catch(() => ({}));
      throw new Error(error.error || 'The request could not be completed. Please try again.');
    }
    return response;
  }
  function updateProgress() {
    const answered = contexts.reduce((count, context) => count + Object.keys(responses[context]).length, 0);
    $('progress').value = answered;
    $('progress-label').textContent = `${answered} of 48 answered`;
  }
  function renderQuestions() {
    show('assessment'); notice();
    const context = contexts[Math.floor(page / 4)];
    const offset = (page % 4) * 6;
    $('phase').textContent = `PHASE ${Math.floor(page / 4) + 1} OF 2 · PAGE ${page % 4 + 1} OF 4`;
    $('context-title').textContent = bank.contexts[context];
    $('context-hint').textContent = context === 'natural'
      ? 'Over the past three months, how often have you done these things in everyday life?'
      : 'Over the past three months, how often have you done these things in your current work role?';
    $('statements').replaceChildren();
    for (const item of bank.items.slice(offset, offset + 6)) {
      const field = document.createElement('fieldset'); field.className = 'statement';
      const legend = document.createElement('legend'); legend.textContent = item.text; field.append(legend);
      const options = document.createElement('div'); options.className = 'rating-options';
      bank.scale.forEach((text, value) => {
        const label = document.createElement('label'); label.className = 'rating-option';
        const input = document.createElement('input');
        input.type = 'radio'; input.name = item.id; input.value = value; input.required = true;
        input.checked = responses[context][item.id] === value;
        input.addEventListener('change', () => { responses[context][item.id] = value; save(); updateProgress(); });
        label.append(input, document.createTextNode(text)); options.append(label);
      });
      field.append(options); $('statements').append(field);
    }
    $('back').textContent = page ? '← Back' : '← Introduction';
    $('next').textContent = page === 7 ? 'Create my report →' : page === 3 ? 'Continue to At work →' : 'Continue →';
    updateProgress(); save(); $('context-title').focus();
  }
  function renderReport() {
    stopAudio(); show('report'); notice(); $('charts').replaceChildren();
    for (const dimension of bank.dimension_order) {
      const info = bank.dimensions[dimension];
      const chart = document.createElement('section'); chart.className = 'chart';
      const title = document.createElement('h2'); title.textContent = `${dimension} · ${info.name}`; chart.append(title);
      for (const context of contexts) {
        const result = report.profiles[context][dimension];
        const label = document.createElement('div'); label.className = 'score-label';
        const score = document.createElement('strong'); score.textContent = `${result.score} / 100`;
        label.append(document.createTextNode(bank.contexts[context]), score);
        const track = document.createElement('div'); track.className = 'bar-track'; track.setAttribute('aria-hidden', 'true');
        const fill = document.createElement('div'); fill.className = 'bar-fill';
        fill.style.width = `${result.score}%`; fill.style.backgroundColor = info.color;
        track.append(fill);
        const frequency = document.createElement('p'); frequency.className = 'frequency'; frequency.textContent = `Answers average ${result.frequency}.`;
        chart.append(label, track, frequency);
      }
      $('charts').append(chart);
    }
    $('section-select').replaceChildren();
    for (const section of report.sections) {
      const option = document.createElement('option'); option.value = section.id; option.textContent = section.title;
      $('section-select').append(option);
    }
    selectSection(); $('report-heading').focus();
  }
  function selectSection() {
    stopAudio();
    $('section-text').textContent = report.sections.find(section => section.id === $('section-select').value).text;
  }
  function stopAudio() {
    generation++; controller?.abort(); controller = null;
    $('audio').pause(); $('audio').removeAttribute('src'); $('audio').load(); $('audio').hidden = true;
    if (audioUrl) URL.revokeObjectURL(audioUrl);
    audioUrl = null; $('listen').disabled = false; $('stop').disabled = true;
    $('mechanics').textContent = 'Answers checked. Scores calculated. Your report is ready.';
  }
  async function listen() {
    stopAudio(); notice(); const current = generation;
    controller = new AbortController(); $('listen').disabled = true; $('stop').disabled = false;
    $('mechanics').textContent = 'Preparing this report section with the local Kokoro voice…';
    try {
      const response = await request(`/audio/${$('section-select').value}`, submission(), controller.signal);
      const blob = await response.blob();
      if (current !== generation) return;
      audioUrl = URL.createObjectURL(blob); $('audio').src = audioUrl; $('audio').hidden = false;
      await $('audio').play();
      if (current === generation) $('mechanics').textContent = 'Speaking the same feedback shown in your report.';
    } catch (error) {
      if (current !== generation) return;
      notice(error.message); $('listen').disabled = false; $('stop').disabled = false;
      $('mechanics').textContent = 'Your report is ready. Retry Listen, or use the audio controls when available.';
    }
  }
  $('begin').addEventListener('click', () => { responses = {natural: {}, adapted: {}}; page = 0; renderQuestions(); });
  $('resume').addEventListener('click', renderQuestions);
  $('back').addEventListener('click', () => {
    if (page) { page--; renderQuestions(); }
    else { show('welcome'); $('resume').hidden = false; }
  });
  $('answers-form').addEventListener('submit', async event => {
    event.preventDefault();
    if (page < 7) { page++; renderQuestions(); return; }
    $('next').disabled = true; $('back').disabled = true; notice();
    try { report = await (await request('/report', submission())).json(); renderReport(); }
    catch (error) { notice(error.message); }
    finally { $('next').disabled = false; $('back').disabled = false; }
  });
  $('section-select').addEventListener('change', selectSection);
  $('listen').addEventListener('click', listen);
  $('stop').addEventListener('click', stopAudio);
  $('audio').addEventListener('ended', () => { $('listen').disabled = false; $('stop').disabled = true; $('mechanics').textContent = 'Section complete. Choose another section or replay this one.'; });
  $('audio').addEventListener('error', () => { if ($('audio').hasAttribute('src')) { notice('This audio could not be played. Try Listen again.'); $('listen').disabled = false; } });
  $('download').addEventListener('click', () => {
    const blob = new Blob([JSON.stringify({...report, questionnaire: bank}, null, 2)], {type: 'application/json'});
    const url = URL.createObjectURL(blob), link = document.createElement('a');
    link.href = url; link.download = 'xq-disc-report.json'; link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
  });
  $('restart').addEventListener('click', () => {
    stopAudio(); report = null; responses = {natural: {}, adapted: {}}; page = 0;
    try { sessionStorage.removeItem(storageKey); } catch { /* The questionnaire still works without browser storage. */ }
    $('resume').hidden = true; show('welcome'); notice(); $('begin').focus();
  });
  window.addEventListener('pagehide', stopAudio);
  request('/questionnaire').then(response => response.json()).then(data => {
    bank = data; $('resume').hidden = !restore(); $('begin').disabled = false;
  }).catch(error => notice(`${error.message} Refresh this page to reconnect.`));
})();
