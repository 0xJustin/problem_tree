// Tree-as-graph renderer for the problem-tree cockpit. Vanilla SVG, no dependencies.
// Visual language: a git commit-graph / git-log row. Each node is a small dot (circle for a
// problem, square for a task) with its id + title flowing to the right on one line, instead of
// a card. Layout: root at the left, children to the right; leaves take fixed vertical slots and
// each parent sits at the middle of its children (tidy enough for a few hundred nodes, never
// overlaps). Pan by dragging, zoom with the wheel; subtrees collapse on the ⊖ handle and new
// nodes animate out of their parent's position. Hovering a node highlights its ancestor chain
// (dots + connecting edges), like tracing a lineage back to the root.
(function () {
  const NS = 'http://www.w3.org/2000/svg';
  const store = typeof localStorage !== 'undefined' ? localStorage : {};
  // NODE_W: how far right a row's furniture (label, rollup badge, collapse toggle) extends before
  // the edge to the next lane departs — purely a layout anchor now, not a drawn box.
  const NODE_W = { problem: 236, task: 200 }, R = 5, DX = 300, DY = 24, PAD = 40;
  const st = { svg: null, g: null, edges: null, nodes: null, tree: null, opts: {}, view: { x: PAD, y: PAD, k: 1 },
    collapsed: new Set(JSON.parse(store.ptCollapsed || '[]')), revealed: new Set(), pos: {}, anim: null, els: new Map(), eels: new Map(),
    offsets: {}, prefix: null, hoverChain: null };
  const loadOffsets = prefix => { st.prefix = prefix; try { st.offsets = JSON.parse(store['ptOffsets:' + prefix] || '{}'); } catch { st.offsets = {}; } };
  const saveOffsets = () => { store['ptOffsets:' + st.prefix] = JSON.stringify(st.offsets); };
  // complete = nothing left to do here: hard-verified or closed problems, done or dropped tasks (soft keeps its todo)
  const isComplete = n => n.type === 'task' ? (n.status === 'done' || n.status === 'dropped') : (n.status === 'closed' || (n.status === 'verified' && n.resolution === 'hard'));

  const el = (tag, attrs, parent) => { const e = document.createElementNS(NS, tag); for (const k in attrs) e.setAttribute(k, attrs[k]); if (parent) parent.appendChild(e); return e; };
  const wrap = (s, width, maxLines = 2) => {
    const lines = []; let line = '', overflow = false;
    for (let w of String(s).split(/\s+/)) {
      if (w.length > width) w = w.slice(0, width - 1) + '…';
      if (line && (line + ' ' + w).length > width) { lines.push(line); line = w; if (lines.length === maxLines) { overflow = true; break; } }
      else line = line ? line + ' ' + w : w;
    }
    if (!overflow && line) lines.push(line);
    if (overflow) lines[maxLines - 1] = lines[maxLines - 1].slice(0, width - 1) + '…';
    return lines;
  };
  const ease = t => 1 - Math.pow(1 - t, 3);

  // ---------------------------------------------------------------- visibility + layout (pure)
  function visibility(tree, state, revealed = st.revealed) {
    const N = tree.nodes, vis = {}, match = {}, folded = {};
    const q = (state.query || '').toLowerCase();
    const hits = n => !q || (n.id + ' ' + n.title + ' ' + (n.aliases || []).join(' ')).toLowerCase().includes(q);
    // a complete node is shown only when asked for globally, or when its parent's ✓ was clicked, or when it matches a search
    const own = n => !(state.hideTasks && n.type === 'task') && !(isComplete(n) && !state.showComplete && !revealed.has(n.parent) && !(q && hits(n)));
    const rec = id => { const n = N[id]; match[id] = hits(n); let v = own(n); let f = 0;
      for (const c of n.children) { v = rec(c) || v; if (!vis[c]) f += 1 + countAll(c); else f += folded[c]; }
      folded[id] = f; return vis[id] = v; };
    const countAll = id => N[id].children.reduce((a, c) => a + 1 + countAll(c), 0);
    if (tree.root) rec(tree.root);
    return { vis, match, folded };
  }
  function layout(tree, state, collapsed, revealed) {
    const N = tree.nodes, { vis, match, folded } = visibility(tree, state, revealed), out = {}, hidden = {};
    let slot = 0;
    const count = id => N[id].children.reduce((a, c) => a + 1 + count(c), 0);
    const place = (id, depth) => {
      const n = N[id], kids = collapsed.has(id) ? [] : n.children.filter(c => vis[c]);
      if (collapsed.has(id)) hidden[id] = count(id);
      if (!kids.length) { out[id] = { x: depth * DX, y: slot * DY, depth }; slot++; return; }
      kids.forEach(c => place(c, depth + 1));
      out[id] = { x: depth * DX, y: (out[kids[0]].y + out[kids[kids.length - 1]].y) / 2, depth };
    };
    if (tree.root && vis[tree.root]) place(tree.root, 0);
    return { pos: out, hidden, match, vis, folded };
  }

  // ---------------------------------------------------------------- lineage highlight (hover)
  function lineageChain(id) {
    const N = st.tree && st.tree.nodes, out = []; let cur = id;
    while (cur && N[cur]) { out.push(cur); cur = N[cur].parent; }
    return out;
  }
  function clearLineage() {
    if (!st.hoverChain) return;
    for (const id of st.hoverChain) st.els.get(id)?.classList.remove('lineage');
    for (let i = 0; i < st.hoverChain.length - 1; i++) st.eels.get(st.hoverChain[i])?.classList.remove('lineage');
    st.hoverChain = null;
  }
  function hoverLineage(id) {
    clearLineage();
    const chain = lineageChain(id);
    st.hoverChain = chain;
    for (const nid of chain) st.els.get(nid)?.classList.add('lineage');
    for (let i = 0; i < chain.length - 1; i++) st.eels.get(chain[i])?.classList.add('lineage');
  }

  // ---------------------------------------------------------------- drawing
  function nodeEl(n, L) {
    const g = el('g', { class: 'gnode', 'data-id': n.id });
    el('rect', { class: 'catsw', x: -19, y: -3, width: 6, height: 6, rx: 1, style: 'display:none' }, g);
    if (n.type === 'task') el('rect', { class: 'shape', x: -5, y: -5, width: 10, height: 10, rx: 2 }, g);
    else el('circle', { class: 'shape', cx: 0, cy: 0, r: R }, g);
    // id + title flow on one line via tspans, like a git-log row: "cbe-yrsu  Connectome body eval…"
    const idChars = n.id.length + 2, totalChars = n.type === 'task' ? 38 : 44;
    const [titleLine = ''] = wrap(n.title, Math.max(10, totalChars - idChars), 1);
    const label = el('text', { x: 11, y: 4, class: 'glabel' }, g);
    const tid = el('tspan', { class: 'gid' }, label); tid.textContent = n.id + '  ';
    el('tspan', { class: 'gtitle' }, label).textContent = titleLine;
    const rightX = NODE_W[n.type] || NODE_W.problem;
    const badge = el('text', { x: rightX - 14, y: 4, class: 'gbadge', 'text-anchor': 'end' }, g);
    const tip = el('title', {}, g); tip.textContent = `${n.id} · ${n.type} · ${n.status}${n.resolution ? ' · ' + n.resolution : ''}\n${n.title}`;
    if (n.children.length) {
      const tg = el('g', { class: 'toggle', transform: `translate(${rightX},0)` }, g);
      el('circle', { r: 9 }, tg);
      el('text', { y: 4, 'text-anchor': 'middle', class: 'tglyph' }, tg);
      el('text', { x: 14, y: 4, class: 'tcount' }, tg);
      tg.addEventListener('click', e => { e.stopPropagation(); tg.classList.contains('fold') ? reveal(n.id) : toggle(n.id); });
    }
    g.addEventListener('click', e => { e.stopPropagation(); if (st.dragged) return; st.opts.onSelect && st.opts.onSelect(n.id); });
    g.addEventListener('pointerdown', e => { if (e.button !== 0 || e.target.closest('.toggle')) return; st.nodeDrag = { id: n.id, x: e.clientX, y: e.clientY, moved: false, start: {} }; });
    g.addEventListener('pointerenter', () => hoverLineage(n.id));
    g.addEventListener('pointerleave', clearLineage);
    return g;
  }
  // real pixel measurement, not a character-count guess: shrink the title tspan until the whole
  // label (id + title) fits before whatever furniture sits at the row's right edge (the rollup
  // badge and/or the collapse toggle) — guarantees no overlap regardless of font/zoom/content.
  function fitLabel(g, n) {
    const label = g.querySelector('.glabel'), tspan = g.querySelector('.gtitle');
    if (!label || !tspan) return;
    const rightX = NODE_W[n.type] || NODE_W.problem;
    const badge = g.querySelector('.gbadge'), badgeText = badge && badge.textContent;
    const badgeLeft = badgeText ? rightX - 14 - badge.getComputedTextLength() - 8 : Infinity;
    const toggleLeft = n.children.length ? rightX - 9 - 6 : Infinity;
    const avail = Math.min(badgeLeft, toggleLeft, rightX - 6) - 11;
    let guard = 0;
    while (label.getComputedTextLength() > avail && tspan.textContent.length > 1 && guard++ < 60) {
      tspan.textContent = tspan.textContent.slice(0, -2) + '…';
    }
  }
  function decorate(g, n, L, state) {
    const rl = n.label ? n.label : '';
    const c = n.rollup || {}, parts = ['open', 'soft', 'collapse', 'tasks'].filter(k => c[k]).map(k => `${k}:${c[k]}`);
    g.setAttribute('class', `gnode ${n.type} ${n.status}${n.resolution ? ' res-' + n.resolution : ''}${rl ? ' rl-' + rl : ''}${n.id === state.selected ? ' sel' : ''}${L.match[n.id] === false ? ' dim' : ''}${st.hoverChain && st.hoverChain.includes(n.id) ? ' lineage' : ''}`);
    const badge = g.querySelector('.gbadge');
    // one word on the row; the numbers live in the tooltip
    badge.textContent = n.children.length ? rl : (n.type === 'task' ? n.status : (n.resolution || (n.status === 'verified' ? '' : n.status)));
    const catsw = g.querySelector('.catsw'), catColor = n.category && state.catColor && state.catColor(n.category);
    if (catsw) { catsw.style.display = catColor ? '' : 'none'; if (catColor) catsw.setAttribute('fill', catColor); }
    const tip = g.querySelector('title');
    if (tip) tip.textContent = `${n.id} · ${n.type} · ${n.status}${n.resolution ? ' · ' + n.resolution : ''}${parts.length ? '\n↓ ' + parts.join('  ') : ''}\n${n.title}`;
    const tg = g.querySelector('.toggle');
    if (tg) {
      const col = st.collapsed.has(n.id), visKids = n.children.filter(c => L.vis[c]).length, fold = !col && !visKids && L.folded[n.id] > 0;
      // ⊖ / ⊕ for collapsing visible children; a green ✓ with a count when every child is complete and folded away
      tg.classList.toggle('col', col); tg.classList.toggle('fold', fold); tg.classList.toggle('open', st.revealed.has(n.id) && !fold);
      tg.querySelector('.tglyph').textContent = fold ? '✓' : (col ? '+' : '−');
      tg.querySelector('.tcount').textContent = col ? L.hidden[n.id] : (fold ? L.folded[n.id] : (L.folded[n.id] && !st.revealed.has(n.id) ? L.folded[n.id] : ''));
      tg.querySelector('title')?.remove();
      const tip = el('title', {}, tg); tip.textContent = fold ? `${L.folded[n.id]} complete, folded — click to show` : (col ? `${L.hidden[n.id]} hidden — click to expand` : (L.folded[n.id] ? `collapse · ${L.folded[n.id]} complete folded` : 'collapse'));
    }
  }
  function edgePath(p, pn, c, cn) {  // dot-center to dot-center, jogging between lanes like a git graph
    const x0 = p.x + (NODE_W[pn.type] || NODE_W.problem), y0 = p.y, x1 = c.x, y1 = c.y, mx = (x0 + x1) / 2;
    return `M${x0},${y0} C${mx},${y0} ${mx},${y1} ${x1},${y1}`;
  }
  function discPath(a, an, b, bn) {  // discovered_from: from the source dot's underside to the target dot's left side
    const x0 = a.x, y0 = a.y + R + 3, x1 = b.x - R - 3, y1 = b.y;
    return `M${x0},${y0} C${x0},${(y0 + y1) / 2} ${x1 - 40},${y1} ${x1},${y1}`;
  }

  function render(tree, state) {
    st.tree = tree;
    if (tree.prefix !== st.prefix) loadOffsets(tree.prefix);
    const N = tree.nodes, L = layout(tree, state, st.collapsed, st.revealed), target = L.pos, ids = Object.keys(target);
    for (const id of ids) { const o = st.offsets[id]; if (o) { target[id] = { ...target[id], x: target[id].x + o.x, y: target[id].y + o.y }; } }
    // nodes: create / update / remove
    for (const id of ids) {
      let g = st.els.get(id), isNew = !g;
      if (!g) { g = nodeEl(N[id], L); st.nodes.appendChild(g); st.els.set(id, g);
        const par = N[id].parent && (st.pos[N[id].parent] || target[N[id].parent]); st.pos[id] = par ? { ...par } : { ...target[id] }; }
      decorate(g, N[id], L, state);
      if (isNew) fitLabel(g, N[id]);
    }
    for (const [id, g] of st.els) if (!target[id]) { g.remove(); st.els.delete(id); delete st.pos[id]; }
    // edges (keyed by child id; discovered_from keyed by 'd:' + id)
    const want = new Set();
    for (const id of ids) {
      const n = N[id];
      if (n.parent && target[n.parent]) { want.add(id); if (!st.eels.has(id)) st.eels.set(id, el('path', { class: 'edge' }, st.edges)); }
      if (state.showDiscovered && n.discovered_from && target[n.discovered_from]) { const k = 'd:' + id; want.add(k); if (!st.eels.has(k)) st.eels.set(k, el('path', { class: 'edge disc', 'marker-end': 'url(#arrow)' }, st.edges)); }
    }
    for (const [k, p] of st.eels) if (!want.has(k)) { p.remove(); st.eels.delete(k); }
    animate(target, N);
    if (state.fit) fit(target);
    else if (state.center) centerOn(state.center, target);
  }
  function draw(pos, N) {
    for (const [id, g] of st.els) { const p = pos[id]; if (p) g.setAttribute('transform', `translate(${p.x},${p.y})`); }
    for (const [k, path] of st.eels) {
      if (k.startsWith('d:')) { const id = k.slice(2), n = N[id], s = pos[n.discovered_from], t = pos[id]; if (s && t) path.setAttribute('d', discPath(s, N[n.discovered_from], t, n)); }
      else { const n = N[k], p = pos[n.parent], c = pos[k]; if (p && c) path.setAttribute('d', edgePath(p, N[n.parent], c, n)); }
    }
  }
  function animate(target, N) {
    const from = {}; for (const id in target) from[id] = st.pos[id] || target[id];
    const same = Object.keys(target).every(id => from[id].x === target[id].x && from[id].y === target[id].y);
    if (st.anim) cancelAnimationFrame(st.anim);
    if (same) { st.pos = target; draw(target, N); return; }
    const t0 = performance.now(), dur = 320;
    const step = now => {
      const t = ease(Math.min(1, (now - t0) / dur)), cur = {};
      for (const id in target) cur[id] = { x: from[id].x + (target[id].x - from[id].x) * t, y: from[id].y + (target[id].y - from[id].y) * t };
      draw(cur, N); st.pos = cur;
      if (t < 1) st.anim = requestAnimationFrame(step); else { st.pos = target; st.anim = null; }
    };
    st.anim = requestAnimationFrame(step);
  }
  function toggle(id) {
    st.collapsed.has(id) ? st.collapsed.delete(id) : st.collapsed.add(id);
    store.ptCollapsed = JSON.stringify([...st.collapsed]);
    st.opts.onChange && st.opts.onChange();
  }
  function subtree(id) { const N = st.tree.nodes, out = [id]; for (const c of N[id].children) out.push(...subtree(c)); return out; }
  function resetLayout() { st.offsets = {}; saveOffsets(); st.opts.onChange && st.opts.onChange(); }
  function reveal(id) {  // show / hide this node's completed children
    st.revealed.has(id) ? st.revealed.delete(id) : st.revealed.add(id);
    st.opts.onChange && st.opts.onChange();
  }
  function expandTo(id) {  // make sure a node is visible: un-collapse its ancestors, reveal it if it is complete
    const N = st.tree && st.tree.nodes; if (!N || !N[id]) return false;
    let changed = false, cur = N[id].parent;
    if (isComplete(N[id]) && cur && !st.revealed.has(cur)) { st.revealed.add(cur); changed = true; }
    while (cur) { if (st.collapsed.delete(cur)) changed = true; if (isComplete(N[cur]) && N[cur].parent && !st.revealed.has(N[cur].parent)) { st.revealed.add(N[cur].parent); changed = true; } cur = N[cur].parent; }
    if (changed) store.ptCollapsed = JSON.stringify([...st.collapsed]);
    return changed;
  }

  // ---------------------------------------------------------------- pan / zoom
  function apply() { st.g.setAttribute('transform', `translate(${st.view.x},${st.view.y}) scale(${st.view.k})`); }
  function zoomToBounds(x0, y0, x1, y1, maxK) {
    const r = st.svg.getBoundingClientRect(), k = Math.min(maxK || 1.4, (r.width - 2 * PAD) / (x1 - x0), (r.height - 2 * PAD) / (y1 - y0));
    st.view = { k, x: PAD - x0 * k + ((r.width - 2 * PAD) - (x1 - x0) * k) / 2, y: PAD - y0 * k + ((r.height - 2 * PAD) - (y1 - y0) * k) / 2 };
    apply();
  }
  function fit(pos) {
    pos = pos || st.pos;
    const ids = Object.keys(pos); if (!ids.length) return;
    let x0 = 1e9, y0 = 1e9, x1 = -1e9, y1 = -1e9;
    for (const id of ids) {
      const p = pos[id], n = st.tree.nodes[id], w = NODE_W[n.type] || NODE_W.problem;
      x0 = Math.min(x0, p.x - R); y0 = Math.min(y0, p.y - 10); x1 = Math.max(x1, p.x + w + 16); y1 = Math.max(y1, p.y + 10);
    }
    zoomToBounds(x0, y0, x1, y1);
  }
  // Center on one node at a comfortable, constant reading zoom (1:1 SVG-to-CSS px) instead of
  // fitting the whole tree — fitting everything is what was making labels tiny by default; "fit"
  // stays available as an explicit zoomed-out overview action via the toolbar button.
  const CENTER_K = 1;
  function centerOn(id, pos) {
    pos = pos || st.pos;
    const p = pos[id]; if (!p || !st.svg) return;
    const n = st.tree.nodes[id], w = (NODE_W[n.type] || NODE_W.problem) / 2;
    const r = st.svg.getBoundingClientRect();
    st.view = { k: CENTER_K, x: r.width / 2 - (p.x + w) * CENTER_K, y: r.height / 2 - p.y * CENTER_K };
    apply();
  }
  function mount(svg, opts) {
    st.svg = svg; st.opts = opts || {};
    const defs = el('defs', {}, svg);
    const m = el('marker', { id: 'arrow', viewBox: '0 0 10 10', refX: 9, refY: 5, markerWidth: 7, markerHeight: 7, orient: 'auto-start-reverse' }, defs);
    el('path', { d: 'M0,0 L10,5 L0,10 z', class: 'arrowhead' }, m);
    st.g = el('g', { class: 'view' }, svg); st.edges = el('g', { class: 'edges' }, st.g); st.nodes = el('g', { class: 'nodes' }, st.g);
    apply();
    // Pan starts only after a few px of movement, so plain clicks still reach the nodes.
    let drag = null;
    svg.addEventListener('pointerdown', e => { if (e.button !== 0 || st.nodeDrag) return; drag = { x: e.clientX, y: e.clientY, vx: st.view.x, vy: st.view.y, id: e.pointerId, moved: false }; });
    svg.addEventListener('pointermove', e => {
      const nd = st.nodeDrag;
      if (nd) {  // move a node and its subtree; edges follow live
        const dx = (e.clientX - nd.x) / st.view.k, dy = (e.clientY - nd.y) / st.view.k;
        if (!nd.moved) { if (Math.hypot(dx, dy) * st.view.k < 5) return; nd.moved = true; svg.setPointerCapture(e.pointerId); nd.ids = subtree(nd.id).filter(i => st.pos[i]); nd.ids.forEach(i => { nd.start[i] = { ...st.pos[i] }; }); st.els.get(nd.id)?.classList.add('moving'); if (st.anim) { cancelAnimationFrame(st.anim); st.anim = null; } }
        for (const i of nd.ids) st.pos[i] = { ...nd.start[i], x: nd.start[i].x + dx, y: nd.start[i].y + dy };
        draw(st.pos, st.tree.nodes); return;
      }
      if (!drag) return;
      const dx = e.clientX - drag.x, dy = e.clientY - drag.y;
      if (!drag.moved) { if (Math.hypot(dx, dy) < 6) return; drag.moved = true; svg.setPointerCapture(drag.id); svg.classList.add('dragging'); }
      st.view.x = drag.vx + dx; st.view.y = drag.vy + dy; apply();
    });
    const end = e => {
      const nd = st.nodeDrag;
      if (nd) {
        if (nd.moved) { const dx = (e.clientX - nd.x) / st.view.k, dy = (e.clientY - nd.y) / st.view.k;
          for (const i of nd.ids) { const o = st.offsets[i] || { x: 0, y: 0 }; st.offsets[i] = { x: o.x + dx, y: o.y + dy }; }
          saveOffsets(); st.dragged = true; setTimeout(() => { st.dragged = false; }, 0); st.els.get(nd.id)?.classList.remove('moving'); }
        st.nodeDrag = null; return;
      }
      if (drag && drag.moved) { st.dragged = true; setTimeout(() => { st.dragged = false; }, 0); } drag = null; svg.classList.remove('dragging'); };
    svg.addEventListener('pointerup', end); svg.addEventListener('pointercancel', end);
    svg.addEventListener('wheel', e => { e.preventDefault(); const r = svg.getBoundingClientRect(), mx = e.clientX - r.left, my = e.clientY - r.top;
      const k = Math.max(0.15, Math.min(3, st.view.k * Math.exp(-e.deltaY * 0.0015)));
      st.view.x = mx - (mx - st.view.x) * k / st.view.k; st.view.y = my - (my - st.view.y) * k / st.view.k; st.view.k = k; apply(); }, { passive: false });
    svg.addEventListener('dblclick', e => { if (e.target === svg || e.target.closest('.edges')) fit(); });
  }

  const Graph = { mount, render, fit, centerOn, toggle, reveal, expandTo, resetLayout, layout, visibility, isComplete, collapsed: st.collapsed, revealed: st.revealed, hasOffsets: () => Object.keys(st.offsets).length > 0 };
  if (typeof module !== 'undefined' && module.exports) module.exports = Graph; else window.Graph = Graph;
})();
