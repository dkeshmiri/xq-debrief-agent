'use strict';
(() => {
  const $ = id => document.getElementById(id);
  const base = $('main').dataset.base;
  const mode = $('main').dataset.mode;
  const ranking = mode === 'ranking', hybrid = mode === 'hybrid';
  const storageKey = {frequency: 'xq-disc-frequency-pilot', ranking: 'xq-disc-scenario-pilot', hybrid: 'xq-disc-hybrid-pilot'}[mode];
  const contexts = ['natural', 'adapted'];
  let bank, report, page = 0, responses = {natural: {}, adapted: {}};
  let controller, audioUrl, generation = 0;
  const pageSize = ranking || hybrid ? 1 : 6;
  const pagesPerContext = () => Math.ceil(bank.items.length / pageSize);
  const totalPages = () => pagesPerContext() * contexts.length;
  const currentContext = () => contexts[Math.floor(page / pagesPerContext())];
  function validRanking(value) {
    return Array.isArray(value) && value.length <= 4 && new Set(value).size === value.length &&
      value.every(id => bank.dimension_order.includes(id));
  }
  const validRating = value => Number.isInteger(value) && value >= 0 && value <= 4;
  function validAnswer(value) {
    if (ranking) return validRanking(value);
    if (!hybrid) return validRating(value);
    return value && typeof value === 'object' && Object.keys(value).length === 2 &&
      value.ratings && typeof value.ratings === 'object' && !Array.isArray(value.ratings) &&
      Object.entries(value.ratings).every(([id, rating]) => bank.dimension_order.includes(id) && validRating(rating)) &&
      (value.first === '' || bank.dimension_order.includes(value.first));
  }
  function completeAnswer(value) {
    if (ranking) return validRanking(value) && value.length === 4;
    if (!hybrid) return validRating(value);
    return validAnswer(value) && Object.keys(value.ratings).length === 4 && bank.dimension_order.includes(value.first);
  }

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
      if (!saved || saved.version !== bank.version || !Number.isInteger(saved.page) || saved.page < 0 || saved.page >= totalPages()) return false;
      const ids = new Set(bank.items.map(item => item.id));
      if (!saved.responses || Object.keys(saved.responses).length !== 2) return false;
      if (!contexts.every(context => {
        const answers = saved.responses[context];
        return answers && typeof answers === 'object' && !Array.isArray(answers) &&
          Object.entries(answers).every(([id, value]) => ids.has(id) && validAnswer(value));
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
    const answered = contexts.reduce((count, context) => count + Object.values(responses[context]).filter(completeAnswer).length, 0);
    $('progress').max = bank.items.length * contexts.length;
    $('progress').value = answered;
    $('progress-label').textContent = `${answered} of ${$('progress').max} ${hybrid ? 'situations completed' : ranking ? 'ranked' : 'answered'}`;
  }
  function ratingField(id, text, selected, onChange) {
    const field = document.createElement('fieldset'); field.className = 'statement';
    const legend = document.createElement('legend'); legend.textContent = text; field.append(legend);
    const options = document.createElement('div'); options.className = 'rating-options';
    bank.scale.forEach((text, value) => {
      const label = document.createElement('label'); label.className = 'rating-option';
      const input = document.createElement('input');
      input.type = 'radio'; input.name = id; input.value = value; input.required = true;
      input.checked = selected === value;
      input.addEventListener('change', () => { onChange(value); save(); updateProgress(); });
      label.append(input, document.createTextNode(text)); options.append(label);
    });
    field.append(options);
    return field;
  }
  function renderHybrid(context, item) {
    const answer = responses[context][item.id] ||= {ratings: {}, first: ''};
    const wording = context === 'adapted' ? item.adapted : item;
    const title = document.createElement('h2'); title.textContent = `${wording.stem}…`;
    const hint = document.createElement('p'); hint.textContent = 'When this situation comes up, how often do you use each behavior? You can use the same rating more than once.';
    $('statements').append(title, hint);
    const shift = (page % bank.items.length + contexts.indexOf(context)) % 4;
    const order = bank.dimension_order.slice(shift).concat(bank.dimension_order.slice(0, shift));
    for (const id of order) {
      $('statements').append(ratingField(id, wording.options[id], answer.ratings[id], value => { answer.ratings[id] = value; }));
    }
    const field = document.createElement('div'); field.className = 'statement';
    const label = document.createElement('label'); label.htmlFor = 'first-approach'; label.textContent = 'Which approach would you start with?';
    const select = document.createElement('select'); select.id = 'first-approach'; select.required = true;
    const placeholder = document.createElement('option'); placeholder.value = ''; placeholder.textContent = 'Choose your first approach…'; select.append(placeholder);
    for (const id of order) {
      const option = document.createElement('option'); option.value = id; option.textContent = wording.options[id]; select.append(option);
    }
    select.value = answer.first;
    select.addEventListener('change', () => { answer.first = select.value; save(); updateProgress(); });
    field.append(label, select); $('statements').append(field);
  }
  function renderRanking(context, item, focusId) {
    const selected = responses[context][item.id] || [];
    const wording = context === 'adapted' ? item.adapted : item;
    $('statements').replaceChildren();
    const field = document.createElement('fieldset'); field.className = 'statement';
    const legend = document.createElement('legend'); legend.textContent = `${wording.stem}…`; field.append(legend);
    const hint = document.createElement('p'); hint.textContent = 'Select all four in order, from most to least like you. Select a ranked card again to remove it.'; field.append(hint);
    const choices = document.createElement('div'); choices.className = 'ranking-options';
    // A balanced rotation varies screen positions without changing answer identities.
    const shift = (page % bank.items.length + contexts.indexOf(context)) % 4;
    const order = bank.dimension_order.slice(shift).concat(bank.dimension_order.slice(0, shift));
    function update(next, focus) {
      responses[context][item.id] = next; save(); updateProgress(); renderRanking(context, item, focus);
    }
    for (const id of order) {
      const position = selected.indexOf(id);
      const button = document.createElement('button'); button.type = 'button'; button.className = 'ranking-option';
      button.id = `rank-${id}`; button.setAttribute('aria-pressed', String(position >= 0));
      button.setAttribute('aria-label', `${wording.options[id]}${position >= 0 ? `, rank ${position + 1}: ${bank.rank_labels[position]}` : ', unranked'}`);
      const badge = document.createElement('span'); badge.className = 'rank-badge'; badge.textContent = position < 0 ? '＋' : position + 1;
      const text = document.createElement('span'); text.textContent = wording.options[id];
      const rankLabel = document.createElement('small'); rankLabel.textContent = position < 0 ? 'Select to rank' : bank.rank_labels[position]; text.append(rankLabel);
      button.append(badge, text); button.addEventListener('click', () => update(position >= 0 ? selected.filter(value => value !== id) : [...selected, id], button.id)); choices.append(button);
    }
    field.append(choices);
    const status = document.createElement('p'); status.setAttribute('role', 'status'); status.textContent = `${selected.length} of 4 ranked${selected.length === 4 ? ' · Ready to continue' : ''}`; field.append(status);
    const actions = document.createElement('div'); actions.className = 'actions';
    for (const [id, label, next] of [['undo-ranking', 'Undo last choice', selected.slice(0, -1)], ['clear-ranking', 'Clear ranking', []]]) {
      const button = document.createElement('button'); button.id = id; button.type = 'button'; button.className = 'button quiet'; button.textContent = label; button.disabled = !selected.length;
      button.addEventListener('click', () => update(next, id)); actions.append(button);
    }
    field.append(actions); $('statements').append(field); $('next').disabled = selected.length !== 4;
    if (focusId) { const target = $(focusId); (target && !target.disabled ? target : choices.firstChild).focus(); }
  }
  function renderQuestions() {
    show('assessment'); notice();
    const context = currentContext();
    const offset = (page % pagesPerContext()) * pageSize;
    $('phase').textContent = `PHASE ${Math.floor(page / pagesPerContext()) + 1} OF 2 · ${ranking || hybrid ? 'SCENARIO' : 'PAGE'} ${page % pagesPerContext() + 1} OF ${pagesPerContext()}`;
    $('context-title').textContent = bank.contexts[context];
    $('context-hint').textContent = ranking ? (context === 'natural'
      ? 'Choose the approaches you naturally prefer when you have the freedom to decide.'
      : 'Think about how you have actually been operating in your current work role over the past three months.') : context === 'natural'
      ? 'Over the past three months, how often have you done these things in everyday life?'
      : 'Over the past three months, how often have you done these things in your current work role?';
    $('statements').replaceChildren();
    $('next').disabled = false;
    if (hybrid) renderHybrid(context, bank.items[offset]);
    else if (ranking) renderRanking(context, bank.items[offset]);
    else for (const item of bank.items.slice(offset, offset + pageSize)) {
      $('statements').append(ratingField(item.id, item.text, responses[context][item.id], value => { responses[context][item.id] = value; }));
    }
    $('back').textContent = page ? '← Back' : '← Introduction';
    $('next').textContent = page === totalPages() - 1 ? 'Create my report →' : page === pagesPerContext() - 1 ? `Continue to ${bank.contexts.adapted} →` : 'Continue →';
    updateProgress(); save(); $('context-title').focus();
  }
  function renderReport() {
    stopAudio(); show('report'); notice(); $('charts').replaceChildren();
    if (ranking || hybrid) {
      $('profile-summaries').replaceChildren();
      for (const context of contexts) {
        const card = document.createElement('div'), title = document.createElement('b'), text = document.createElement('p');
        title.textContent = bank.contexts[context]; text.textContent = report.summaries[context]; card.append(title, text); $('profile-summaries').append(card);
      }
    }
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
        const frequency = document.createElement('p'); frequency.className = 'frequency'; frequency.textContent = ranking ? result.description : `Answers average ${result.frequency}.`;
        chart.append(label, track, frequency);
        if (hybrid) {
          const first = document.createElement('p'); first.className = 'frequency first-choice';
          first.textContent = `First approach in ${result.firsts} of ${result.count} situations.`;
          chart.append(first);
        }
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
      const response = await request(`/audio/${$('section-select').value}`, {version: report.version, responses: report.responses}, controller.signal);
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
    if ((ranking || hybrid) && !completeAnswer(responses[currentContext()][bank.items[page % bank.items.length].id])) return;
    if (page < totalPages() - 1) { page++; renderQuestions(); return; }
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
    link.href = url; link.download = {frequency: 'xq-disc-report.json', ranking: 'xq-disc-scenario-report.json', hybrid: 'xq-disc-hybrid-report.json'}[mode]; link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
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
