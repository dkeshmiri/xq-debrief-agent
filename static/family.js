'use strict';
(() => {
    const $ = id => document.getElementById(id);
    const base = document.body?.dataset?.apiBase || '';
    const business = document.body?.dataset?.experience === 'business';
    let busy = false, members = [], comparedGroup = null;
    const scoreLabels = {
        D: 'D · Dominance', I: 'I · Influence', S: 'S · Steadiness', C: 'C · Compliance',
        self_awareness: 'Self-Awareness', self_regulation: 'Self-Regulation',
        motivation: 'Motivation', social_awareness: 'Social Awareness',
        social_regulation: 'Social Regulation', SELF: 'Self', OTHERS: 'Others', TOTAL_EQ: 'Total EQ'
    };
    let choices = [];
    function selection() { return {person_ids: choices.filter(input => input.checked).map(input => input.value)}; }
    function validSelection() { const n = selection().person_ids.length; return n >= 2 && n <= 4; }
    function controls() {
        $('pair-fields').disabled = busy || members.length < 2;
        const count = selection().person_ids.length;
        $('selection-count').textContent = `${count} of 4 members selected`;
        choices.forEach(input => { input.disabled = busy || (count >= 4 && !input.checked); });
        $('compare-button').disabled = busy || !validSelection();
        $('family-question').disabled = busy;
        $('family-ask-button').disabled = busy || !comparedGroup || !$('family-question').value.trim();
    }
    function clearComparison() {
        comparedGroup = null;
        $('comparison-card').hidden = true;
        $('family-question-card').hidden = true;
        $('family-answer-card').hidden = true;
        $('family-answer').textContent = '';
        $('family-question').value = '';
        $('family-error').hidden = true;
        $('family-status').textContent = validSelection() ? 'Ready to compare these profiles.' : (business ? 'Choose two to four team members.' : 'Choose two to four family members.');
        controls();
    }
    async function request(url, body) {
        const response = await fetch(base + url, {
            method: body ? 'POST' : 'GET', headers: {'Content-Type': 'application/json'},
            ...(body ? {body: JSON.stringify(body)} : {}),
            cache: 'no-store', signal: AbortSignal.timeout(body?.question ? 45000 : 10000)
        });
        const result = await response.json();
        if (!response.ok) throw new Error(result.error || (business ? 'The team workspace is unavailable. Please try again.' : 'The family workspace is unavailable. Please try again.'));
        return result;
    }
    async function run(action) {
        if (busy) return;
        busy = true;
        $('family-error').hidden = true;
        controls();
        try { await action(); }
        catch (error) {
            $('family-error').textContent = error.message;
            $('family-error').hidden = false;
            $('family-status').textContent = 'The request could not be completed. You can try again.';
        } finally { busy = false; controls(); }
    }
    function cell(tag, text) {
        const node = document.createElement(tag);
        node.textContent = text;
        return node;
    }
    function table(title, scores, people) {
        const wrap = document.createElement('div');
        wrap.className = 'comparison-table-wrap';
        wrap.tabIndex = 0;
        wrap.setAttribute('role', 'region');
        wrap.setAttribute('aria-label', title);
        const table = document.createElement('table');
        table.appendChild(cell('caption', title));
        const head = document.createElement('thead'), headings = document.createElement('tr');
        for (const label of ['Assessment', ...people.map(person => `${person.display_name} (${person.family_role})`)]) {
            const th = cell('th', label); th.scope = 'col'; headings.appendChild(th);
        }
        head.appendChild(headings); table.appendChild(head);
        const body = document.createElement('tbody');
        for (const [key, value] of Object.entries(scores)) {
            const row = document.createElement('tr'), th = cell('th', scoreLabels[key] || key);
            th.scope = 'row'; row.appendChild(th);
            for (const person of people) row.appendChild(cell('td', String(value[person.person_id])));
            body.appendChild(row);
        }
        table.appendChild(body); wrap.appendChild(table);
        $('comparison-tables').appendChild(wrap);
    }
    $('compare-form').addEventListener('submit', event => {
        event.preventDefault();
        if (busy || !validSelection()) return;
        const selected = selection();
        clearComparison();
        run(async () => {
            $('family-status').textContent = 'Reading the saved assessment facts…';
            const {comparison: data} = await request('/api/family/group/compare', selected);
            $('comparison-tables').replaceChildren();
            $('comparison-title').textContent = data.members.map(person => person.display_name).join(' · ');
            table('DISC · Natural preferences', data.assessments.disc_natural, data.members);
            table('DISC · Adapted preferences', data.assessments.disc_adapted, data.members);
            table('Driving Forces', data.assessments.driving_forces, data.members);
            table('EQ · Dimensions', data.assessments.eq_dimensions, data.members);
            table('EQ · Composites', data.assessments.eq_composites, data.members);
            comparedGroup = selected;
            $('comparison-card').hidden = false;
            $('family-question-card').hidden = false;
            $('family-status').textContent = 'Comparison ready. Explore the facts or ask about these members.';
            $('comparison-title').focus();
        });
    });
    $('family-question-form').addEventListener('submit', event => {
        event.preventDefault();
        if (busy || !comparedGroup || !$('family-question').value.trim()) return;
        run(async () => {
            $('family-answer-card').hidden = true;
            $('family-answer').textContent = '';
            $('family-status').textContent = 'Exploring the selected profiles together…';
            const data = await request('/api/family/group/question', {...comparedGroup, question: $('family-question').value.trim()});
            $('family-answer').textContent = data.answer;
            $('family-answer-card').hidden = false;
            $('family-status').textContent = business ? 'Your team comparison answer is ready.' : 'Your family comparison answer is ready.';
        });
    });
    $('family-question').addEventListener('input', controls);
    run(async () => {
        const data = await request('/api/family');
        members = data.members;
        $('family-name').textContent = data.family_name;
        $('member-choices').replaceChildren();
        choices = members.map((person, index) => {
            const label = document.createElement('label');
            label.className = 'member-choice';
            const input = document.createElement('input');
            input.type = 'checkbox'; input.value = person.person_id; input.checked = index < 2;
            input.addEventListener('change', clearComparison);
            label.appendChild(input);
            label.appendChild(cell('span', `${person.display_name} — ${person.family_role}`));
            $('member-choices').appendChild(label);
            return input;
        });
        $('family-status').textContent = members.length < 2
            ? (business ? 'Save at least two workplace profiles to compare perspectives.' : 'Save at least two enabled family profiles to compare perspectives.')
            : (business ? 'Choose two to four team members, then compare their profiles.' : 'Choose two to four family members, then compare their profiles.');
    });
})();
