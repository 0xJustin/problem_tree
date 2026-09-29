// Storyline timeline: a calendar axis with story points as dots, tasks closed per day as faint
// bars under the axis. Drag or wheel pans, ctrl/pinch-wheel zooms around the cursor.
const Timeline = (() => {
  const DAY = 864e5, H = 176, AXIS = 118, LANES = [92, 66, 40];
  const KIND = {decision: ['var(--acc)', 'decision'], 'problem-exposed': ['var(--open)', 'problem exposed'],
                fix: ['var(--task)', 'fix'], overview: ['var(--prop)', 'overview']};
  const T = {svg: null, points: [], closed: {}, today: null, x0: 0, x1: 0, sel: null, onPick: null};
  const ms = d => Date.parse(String(d).slice(0, 10) + 'T00:00:00Z');
  const color = k => (KIND[k] || ['var(--mute)'])[0];

  function mount(svg, data, sel, onPick) {
    const keep = T.svg === svg && T.x1 > T.x0;  // same strip re-rendered: keep the user's pan/zoom
    Object.assign(T, {svg, points: data.points, closed: data.closed, today: ms(data.today), sel, onPick});
    if (!keep) fit(); else reveal(sel);
    if (!svg.dataset.wired) wire(svg);
    draw();
  }

  function fit() {
    const ts = [...T.points.map(p => ms(p.date)), ...Object.keys(T.closed).map(ms), T.today].filter(Number.isFinite);
    let a = Math.min(...ts) - 4 * DAY, b = T.today + 6 * DAY;
    if (b - a < 35 * DAY) a = b - 35 * DAY;
    T.x0 = a; T.x1 = b;
  }

  function wire(svg) {
    svg.dataset.wired = 1;
    let drag = null;
    svg.addEventListener('pointerdown', e => { drag = {x: e.clientX, x0: T.x0, x1: T.x1, moved: false}; });
    window.addEventListener('pointermove', e => {
      if (!drag) return;
      const dx = e.clientX - drag.x; if (Math.abs(dx) > 3) drag.moved = true;
      if (!drag.moved) return;
      const shift = dx / svg.clientWidth * (drag.x1 - drag.x0);
      T.x0 = drag.x0 - shift; T.x1 = drag.x1 - shift; svg.classList.add('dragging'); draw();
    });
    window.addEventListener('pointerup', () => { if (drag?.moved) svg.dataset.justDragged = 1; drag = null; svg.classList.remove('dragging'); });
    svg.addEventListener('click', e => {
      if (svg.dataset.justDragged) { delete svg.dataset.justDragged; return; }
      const g = e.target.closest('[data-slug]'); if (g && T.onPick) T.onPick(g.dataset.slug);
    });
    svg.addEventListener('wheel', e => {
      e.preventDefault();
      const span = T.x1 - T.x0, w = svg.clientWidth;
      if (e.ctrlKey || e.metaKey) {
        const f = Math.exp(e.deltaY * 0.01), at = T.x0 + (e.offsetX / w) * span;
        const s = Math.min(Math.max(span * f, 7 * DAY), 3 * 365 * DAY);
        T.x0 = at - (at - T.x0) * s / span; T.x1 = T.x0 + s;
      } else {
        const d = (Math.abs(e.deltaX) > Math.abs(e.deltaY) ? e.deltaX : e.deltaY) / w * span;
        T.x0 += d; T.x1 += d;
      }
      draw();
    }, {passive: false});
    svg.addEventListener('dblclick', () => { fit(); draw(); });
    window.addEventListener('resize', () => { if (T.svg?.isConnected) draw(); });
  }

  function ticks(X, W) {
    const span = (T.x1 - T.x0) / DAY, out = [];
    const start = new Date(T.x0); start.setUTCHours(0, 0, 0, 0);
    for (let t = start.getTime(); t <= T.x1; t += DAY) {
      const d = new Date(t), x = X(t), first = d.getUTCDate() === 1, mon = d.getUTCDay() === 1;
      if (first) out.push(`<line x1="${x}" x2="${x}" y1="${AXIS - 9}" y2="${AXIS + 4}" stroke="var(--mute2)"/>
        <text x="${x + 4}" y="${H - 10}" class="tl-month">${d.toLocaleString('en', {month: 'long', timeZone: 'UTC'})} ${d.getUTCFullYear()}</text>`);
      else if (span <= 120 && mon) out.push(`<line x1="${x}" x2="${x}" y1="${AXIS - 4}" y2="${AXIS}" stroke="var(--line2)"/>`
        + (span <= 70 ? `<text x="${x}" y="${AXIS + 16}" class="tl-day">${d.getUTCDate()}</text>` : ''));
      else if (span <= 21) out.push(`<line x1="${x}" x2="${x}" y1="${AXIS - 2}" y2="${AXIS}" stroke="var(--line2)"/><text x="${x}" y="${AXIS + 16}" class="tl-day">${d.getUTCDate()}</text>`);
    }
    // month label for a view that starts mid-month
    const s = new Date(T.x0);
    if (s.getUTCDate() > 1) out.push(`<text x="8" y="${H - 10}" class="tl-month">${s.toLocaleString('en', {month: 'long', timeZone: 'UTC'})} ${s.getUTCFullYear()}</text>`);
    return out.join('');
  }

  function draw() {
    const svg = T.svg, W = svg.clientWidth || 800, X = t => (t - T.x0) / (T.x1 - T.x0) * W;
    const barMax = Math.max(1, ...Object.values(T.closed));
    let h = `<rect x="0" y="0" width="${W}" height="${H}" fill="transparent"/>`;
    for (const [d, n] of Object.entries(T.closed)) {
      const x = X(ms(d) + DAY / 2), bw = Math.max(2, Math.min(10, W / ((T.x1 - T.x0) / DAY) * 0.6));
      h += `<rect x="${x - bw / 2}" y="${AXIS + 22}" width="${bw}" height="${2 + 22 * n / barMax}" rx="1" fill="var(--line)"><title>${d} · ${n} closed</title></rect>`;
    }
    h += `<line x1="0" x2="${W}" y1="${AXIS}" y2="${AXIS}" stroke="var(--line2)" stroke-width="1.5"/>` + ticks(X, W);
    const tx = X(T.today + DAY / 2);
    h += `<line x1="${tx}" x2="${tx}" y1="14" y2="${AXIS + 46}" stroke="var(--acc)" stroke-dasharray="3 3" opacity=".7"/>`;
    // labels: greedy lanes, left to right; a label that fits no lane shows on hover only
    const sel = T.points.find(p => p.slug === T.sel), linked = new Set(sel ? [sel.answers, ...T.points.filter(p => p.answers === sel.slug).map(p => p.slug)] : []);
    const ends = LANES.map(() => -Infinity), placed = [];
    const order = [...T.points].sort((a, b) => ms(a.date) - ms(b.date));
    for (const p of order) {
      const x = X(ms(p.date) + DAY / 2), label = p.title.length > 38 ? p.title.slice(0, 36) + '…' : p.title, w = label.length * 6.3 + 14;
      const lane = LANES.findIndex((_, i) => ends[i] < x - w / 2);
      if (lane >= 0) ends[lane] = x + w / 2;
      placed.push({p, x, label, lane});
    }
    for (const {p, x, label, lane} of placed) {
      const on = p.slug === T.sel, c = color(p.kind), y = lane >= 0 ? LANES[lane] : null;
      h += `<g data-slug="${esc(p.slug)}" class="tl-pt${on ? ' on' : ''}"><title>${esc(p.date)} · ${esc((KIND[p.kind] || [, p.kind])[1] || '')}\n${esc(p.title)}</title>`
        + (y !== null ? `<line x1="${x}" x2="${x}" y1="${y + 5}" y2="${AXIS - 8}" stroke="${on ? c : 'var(--line2)'}"/>
           <text x="${x}" y="${y}" class="tl-label">${esc(label)}</text>` : '')
        + (on ? `<circle cx="${x}" cy="${AXIS}" r="14" fill="none" stroke="${c}" stroke-opacity=".28" stroke-width="4"/>` : '')
        + (linked.has(p.slug) ? `<circle cx="${x}" cy="${AXIS}" r="11" fill="none" stroke="${c}" stroke-dasharray="2 2"/>` : '')
        + `<circle cx="${x}" cy="${AXIS}" r="${on ? 9 : 6.5}" fill="${c}" stroke="#fff" stroke-width="2.5"/>
           <rect x="${x - 12}" y="${(y ?? AXIS) - 14}" width="24" height="${AXIS - (y ?? AXIS) + 26}" fill="transparent"/></g>`;
    }
    svg.setAttribute('viewBox', `0 0 ${W} ${H}`);
    svg.innerHTML = h;
  }

  function reveal(slug) {  // pan so a point picked from the list or by key is on screen
    const p = T.points.find(q => q.slug === slug); if (!p) return;
    const t = ms(p.date), span = T.x1 - T.x0;
    if (t < T.x0 + span * 0.05 || t > T.x1 - span * 0.05) { T.x0 = t - span / 2; T.x1 = t + span / 2; }
  }

  return {mount, reveal, KIND, color};
})();
