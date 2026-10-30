/* Data-only business graphics. Never interpret supplied text as HTML. */
function renderInvestorVisual(container, chart) {
    function node(tag, text, className) {
        const el = document.createElement(tag);
        el.textContent = text;
        if (className) el.className = className;
        return el;
    }
    const content = node('div', '', `investor-content investor-${chart.layout}`);
    const number = value => value.toLocaleString('en-US', {maximumFractionDigits:2});
    for (const [index, item] of chart.items.entries()) {
        if (chart.layout === 'bars') {
            const group = node('section', '', 'investor-bar-group');
            group.append(node('h3', item.label));
            const maximum = Math.max(1, ...item.bars.map(bar => bar.value));
            const scale = node('div', '', 'investor-scale');
            scale.append(node('span', '0'), node('span', `${number(maximum)} ${item.unit}`));
            group.append(scale);
            for (const [i, bar] of item.bars.entries()) {
                const row = node('div', '', 'investor-bar-row');
                row.append(node('span', bar.label), node('strong', number(bar.value)));
                const track = node('div', '', 'investor-track');
                track.setAttribute('aria-hidden', 'true');
                const fill = node('div', '', 'investor-fill');
                fill.dataset.accent = String(i % 3);
                fill.style.width = `${bar.value / maximum * 100}%`;
                track.append(fill); row.append(track); group.append(row);
            }
            content.append(group);
        } else {
            const card = node('article', '', 'investor-card');
            card.dataset.accent = String(index % 3);
            card.append(node('p', item.label, 'investor-label'), node('strong', item.value, 'investor-value'), node('p', item.detail, 'investor-detail'));
            content.append(card);
        }
    }
    container.append(content, node('p', chart.takeaway, 'investor-takeaway'), node('p', chart.source, 'investor-source'));
}
