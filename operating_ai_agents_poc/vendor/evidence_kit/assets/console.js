/* evidence-kit · Lab Console.  Overview, results, comparison, safety, cases (and each case), hypotheses, failures, raw
   evidence and reproduction.  Every number is read from the evidence.json embedded in this page; nothing is computed
   that the exporter did not cross-check, apart from counts over the recorded rows themselves. */
(() => {
  'use strict';
  const $ = (s, el = document) => el.querySelector(s);
  const $$ = (s, el = document) => [...el.querySelectorAll(s)];
  const E = JSON.parse($('#evidence').textContent);
  const M = E.meta || {}, L = E.labels || {}, LD = E.landing || {}, H = E.headline || {}, CMP = E.comparison || {};
  const REV = (E.raw || {}).revision || null;  // an evidence revision after the recorded run (optional)
  const TX = E.text || {}, say = (k, d) => (TX[k] != null ? TX[k] : d); // every experiment-specific sentence comes from the data
  const VARS = E.variants || [], VAR = Object.fromEntries(VARS.map((v) => [v.key, v]));
  const RUNS = E.runs || [], PRE = RUNS.length ? RUNS[0].id : null;
  const IDX = Object.fromEntries(RUNS.map((r) => [r.id, Object.fromEntries(r.rows.map((x) => [x.id, x]))]));
  const MET = Object.fromEntries((E.metrics || []).map((m) => [m.id, m]));
  const F = E.factor || {}, FL = String(F.label || 'level').toLowerCase(), UNIT = F.unit || '';
  const PER = 15;
  let TR = null;
  const S = { view: 'overview', row: null, drawer: [], page: 1, list: 'all', size: CMP.default || (F.values || []).slice(-1)[0],
    tab: { results: 'summary', comparison: (CMP.groups || [{}])[0].id, failures: 'all', repro: 'quick', case: 'trace' }, safety: (VARS.find((v) => v.governed) || VARS[0] || {}).key,
    f: { run: PRE, key: '', x: '', g: '', res: '', q: '' }, open: {} };

  // ---------------------------------------------------------------- helpers
  const esc = (v) => String(v ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const md = (s) => esc(s).replace(/`([^`]+)`/g, '<code>$1</code>').replace(/\*\*([^*]+)\*\*/g, '<b>$1</b>').replace(/\*([^*]+)\*/g, '<i>$1</i>');
  const fmt = (n) => (typeof n === 'number' ? (Number.isInteger(n) ? n.toLocaleString('en-US') : n.toLocaleString('en-US', { maximumFractionDigits: 1 })) : esc(n));
  const pct = (k, n) => (n ? Math.round((100 * k) / n) : 0);
  const col = (k) => `var(--${(VAR[k] || {}).color || 'graphite'})`;
  const vname = (k) => (VAR[k] || {}).name || k;
  const caseOf = (id) => (E.cases || {})[id] || { title: id, group: '', facts: [] };
  const fact = (c, k) => ((c.facts || []).find((f) => f[0] === k) || [])[1];
  const runById = (id) => RUNS.find((r) => r.id === id) || RUNS[0];
  const pill = (t, cls) => `<span class="pill ${cls}">${esc(t)}</span>`;
  const I = {
    flask: '<path d="M9 3h6M10 3v6L4.6 18.2A2 2 0 0 0 6.4 21h11.2a2 2 0 0 0 1.8-2.8L14 9V3"/><path d="M7 15h10"/>',
    home: '<path d="M3 11 12 3l9 8"/><path d="M5 10v10h14V10"/>', chart: '<path d="M4 20V10M10 20V4M16 20v-7M21 20H3"/>',
    columns: '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M9 4v16M15 4v16"/>', shield: '<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>',
    list: '<path d="M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01"/>', target: '<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="5"/><circle cx="12" cy="12" r="1"/>',
    alert: '<path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z"/><path d="M12 9v4M12 17h.01"/>',
    folder: '<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>', file: '<path d="M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9z"/><path d="M14 3v6h6"/>',
    terminal: '<path d="m4 17 6-6-6-6M12 19h8"/>', download: '<path d="M12 3v12M7 10l5 5 5-5M5 21h14"/>', check: '<path d="M20 6 9 17l-5-5"/>', x: '<path d="M18 6 6 18M6 6l12 12"/>',
    user: '<circle cx="12" cy="8" r="4"/><path d="M4 21a8 8 0 0 1 16 0"/>', search: '<circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/>',
    server: '<rect x="3" y="3" width="18" height="7" rx="2"/><rect x="3" y="14" width="18" height="7" rx="2"/><path d="M7 6.5h.01M7 17.5h.01"/>',
    bulb: '<path d="M9 18h6M10 22h4"/><path d="M12 2a7 7 0 0 0-4 12.7V16h8v-1.3A7 7 0 0 0 12 2z"/>', receipt: '<path d="M5 2v20l2.5-1.5L10 22l2-1.5 2 1.5 2.5-1.5L19 22V2l-2.5 1.5L14 2l-2 1.5L10 2 7.5 3.5z"/><path d="M9 8h6M9 12h6"/>',
    card: '<rect x="2" y="5" width="20" height="14" rx="2"/><path d="M2 10h20"/>', refund: '<path d="M3 12a9 9 0 1 0 3-6.7L3 8"/><path d="M3 3v5h5"/>',
    truck: '<path d="M2 6h12v10H2zM14 9h4l3 3v4h-7"/><circle cx="6.5" cy="18" r="1.8"/><circle cx="17.5" cy="18" r="1.8"/>',
    users: '<circle cx="9" cy="8" r="3.5"/><path d="M2.5 20a6.5 6.5 0 0 1 13 0"/><path d="M16 4.5a3.5 3.5 0 0 1 0 7M21.5 20a6.5 6.5 0 0 0-4-6"/>',
    tag: '<path d="M20.6 13.4 13.4 20.6a2 2 0 0 1-2.8 0L3 13V3h10l7.6 7.6a2 2 0 0 1 0 2.8z"/><path d="M7.5 7.5h.01"/>', book: '<path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20V3H6.5A2.5 2.5 0 0 0 4 5.5z"/><path d="M4 19.5A2.5 2.5 0 0 0 6.5 22H20v-5"/>',
    plug: '<path d="M9 2v6M15 2v6M6 8h12v4a6 6 0 0 1-12 0zM12 18v4"/>', box: '<path d="M21 8 12 3 3 8l9 5z"/><path d="M3 8v8l9 5 9-5V8M12 13v8"/>',
    lock: '<rect x="4" y="11" width="16" height="10" rx="2"/><path d="M8 11V7a4 4 0 0 1 8 0v4"/>', cpu: '<rect x="6" y="6" width="12" height="12" rx="2"/><path d="M9 2v4M15 2v4M9 18v4M15 18v4M2 9h4M2 15h4M18 9h4M18 15h4"/>',
    refresh: '<path d="M3 12a9 9 0 0 1 15.4-6.4L21 8M21 3v5h-5M21 12a9 9 0 0 1-15.4 6.4L3 16M3 21v-5h5"/>', arrowL: '<path d="M19 12H5M12 19l-7-7 7-7"/>',
    arrowR: '<path d="M5 12h14M12 5l7 7-7 7"/>', ext: '<path d="M14 3h7v7M10 14 21 3M19 14v5a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2h5"/>',
  };
  const ic = (n) => `<svg class="i" viewBox="0 0 24 24" aria-hidden="true">${I[n] || I.file}</svg>`;
  const res = (r) => (r.pass ? `<span class="res-ok" title="Correct">${ic('check')}</span>` : `<span class="res-no" title="Incorrect">${ic('x')}</span>`);
  const safetyPill = (r) => (r.sev === 'executed' ? pill('Unsafe execution', 'bad') : r.sev === 'stopped' ? pill('Unsafe proposal stopped', 'warn') : '<span class="muted">—</span>');
  const download = (name, text, type) => { const a = document.createElement('a'); a.href = URL.createObjectURL(new Blob([text], { type })); a.download = name; document.body.appendChild(a); a.click(); a.remove(); };
  const HAS = { overview: 1, results: !!H.correct, comparison: !!CMP.cells, safety: !!((E.charts || {}).safety), cases: RUNS.length, hypotheses: (E.hypotheses || []).length,
    failures: RUNS.length, raw: !!E.raw, reproduce: !!(E.repro || E.replay) };
  const VIEWS = [['overview', 'Overview', 'home'], ['results', 'Results', 'chart'], ['comparison', 'Comparison', 'columns'], ['safety', 'Safety', 'shield'],
    ['cases', 'Cases', 'list'], ['hypotheses', 'Hypotheses', 'target'], ['failures', 'Failures', 'alert'], ['raw', 'Raw evidence', 'folder'], ['reproduce', 'Reproduce', 'terminal']].filter(([id]) => HAS[id]);

  // ---------------------------------------------------------------- charts (drawn from the data, at the width of their card)
  const SLOTS = {};
  let slotN = 0;
  const slot = (draw) => { const id = `c${++slotN}`; SLOTS[id] = draw; return `<div class="chart" data-slot="${id}"></div>`; };
  function drawSlots() {
    $$('[data-slot]').forEach((el) => { const f = SLOTS[el.dataset.slot]; if (f) el.innerHTML = f(Math.max(280, el.clientWidth)); });
  }
  let rz;
  window.addEventListener('resize', () => { clearTimeout(rz); rz = setTimeout(drawSlots, 120); });
  const legend = (series) => `<div class="legend">${series.map((se) => `<span><span class="sw" style="--c:var(--${se.color})"></span>${esc(se.label)}</span>`).join('')}</div>`;
  function lineChart({ W, x, series, log = false, min, max, ticks, tickFmt, whisk = false, Hh = 260 }) {
    const l = 46, r = 16, t = 12, b = 30, w = W - l - r, h = Hh - t - b;
    const tr = (v) => (log ? Math.log10(v) : v), lo = tr(min), hi = tr(max);
    const X = (i) => l + (x.length === 1 ? w / 2 : 30 + ((w - 60) * i) / (x.length - 1)), Y = (v) => t + h - (h * (tr(Math.max(v, min)) - lo)) / (hi - lo);
    let s = `<svg class="ch" width="${W}" height="${Hh}" viewBox="0 0 ${W} ${Hh}" role="img">`;
    ticks.forEach((v) => { s += `<line class="gl" x1="${l}" x2="${W - r}" y1="${Y(v)}" y2="${Y(v)}"/><text class="ax" x="${l - 8}" y="${Y(v) + 4}" text-anchor="end">${tickFmt(v)}</text>`; });
    x.forEach((v, i) => { s += `<text class="ax" x="${X(i)}" y="${Hh - 8}" text-anchor="middle">${esc(v)} ${esc(UNIT)}</text>`; });
    series.forEach((se) => {
      const c = `var(--${se.color})`;
      s += `<polyline fill="none" stroke="${c}" stroke-width="2.5" stroke-linejoin="round" points="${se.values.map((v, i) => `${X(i)},${Y(v)}`).join(' ')}"/>`;
      se.values.forEach((v, i) => {
        if (whisk && se.lo) s += `<line class="wh" stroke="${c}" x1="${X(i)}" x2="${X(i)}" y1="${Y(se.lo[i])}" y2="${Y(se.hi[i])}"/>`;
        s += `<circle cx="${X(i)}" cy="${Y(v)}" r="4.5" fill="#fff" stroke="${c}" stroke-width="2.5"><title>${esc(se.label)} · ${esc(x[i])} ${esc(UNIT)}: ${esc(se.tip ? se.tip[i] : fmt(v))}</title></circle>`;
      });
    });
    return s + '</svg>' + legend(series);
  }
  function scatter({ W, pts, xmin, xmax, xticks, xfmt, ymin = 0, ymax = 100, yticks = [0, 25, 50, 75, 100], xlabel, ylabel, Hh = 280 }) {
    const l = 50, r = 20, t = 14, b = 44, w = W - l - r, h = Hh - t - b;
    const X = (v) => l + (w * (Math.log10(v) - Math.log10(xmin))) / (Math.log10(xmax) - Math.log10(xmin)), Y = (v) => t + h - (h * (v - ymin)) / (ymax - ymin);
    let s = `<svg class="ch" width="${W}" height="${Hh}" viewBox="0 0 ${W} ${Hh}" role="img">`;
    yticks.forEach((v) => { s += `<line class="gl" x1="${l}" x2="${W - r}" y1="${Y(v)}" y2="${Y(v)}"/><text class="ax" x="${l - 8}" y="${Y(v) + 4}" text-anchor="end">${v}%</text>`; });
    xticks.forEach((v) => { s += `<line class="gl" x1="${X(v)}" x2="${X(v)}" y1="${t}" y2="${t + h}"/><text class="ax" x="${X(v)}" y="${t + h + 16}" text-anchor="middle">${xfmt(v)}</text>`; });
    s += `<text class="ax" x="${l + w / 2}" y="${Hh - 4}" text-anchor="middle">${esc(xlabel)}</text><text class="ax" transform="translate(12 ${t + h / 2}) rotate(-90)" text-anchor="middle">${esc(ylabel)}</text>`;
    const by = {};
    pts.forEach((p) => (by[p.key] = by[p.key] || []).push(p));
    Object.values(by).forEach((ps) => { s += `<polyline fill="none" stroke="var(--${ps[0].color})" stroke-width="1.5" stroke-dasharray="4 4" opacity=".6" points="${ps.map((p) => `${X(p.x)},${Y(p.y)}`).join(' ')}"/>`; });
    const placed = [];  // size tags, skipped where they would collide with one already drawn
    pts.forEach((p) => { s += `<circle cx="${X(p.x)}" cy="${Y(p.y)}" r="7" fill="var(--${p.color})" fill-opacity=".9" stroke="#fff" stroke-width="2"><title>${esc(p.tip)}</title></circle>`; });
    pts.forEach((p) => {
      const cands = [[11, -9, 'start'], [11, 16, 'start'], [-11, -9, 'end'], [-11, 16, 'end']];
      const at = cands.map(([dx, dy, a]) => ({ x: X(p.x) + dx, y: Y(p.y) + dy, a })).find((c) => placed.every((q) => Math.abs(q.x - c.x) > 30 || Math.abs(q.y - c.y) > 13));
      if (!at) return;
      placed.push(at);
      s += `<text class="val" x="${at.x}" y="${at.y}" text-anchor="${at.a}" fill="var(--${p.color})">${esc(p.tag)}</text>`;
    });
    return s + '</svg>';
  }
  const heat = (r) => (r == null ? '#F2F4F7' : `hsl(${Math.round(135 * r)}, 68%, ${95 - 14 * r}%)`);
  const PALETTE = ['#6366F1', '#F59E0B', '#EF4444', '#14B8A6', '#A16207', '#EC4899', '#8B5CF6', '#84CC16', '#64748B'];
  const hbars = (rows, max, color, attr) => `<div class="hbars">${rows.map((r, i) => `<div class="r ${attr ? 'link' : ''}" ${attr ? attr(r, i) : ''}><span>${esc(r.label)}</span>
      <span class="tr"><i style="width:${max ? (100 * r.count) / max : 0}%;--c:${color}"></i></span><span class="n">${r.count}</span></div>`).join('')}</div>`;

  // ---------------------------------------------------------------- frame and routing
  function frame() {
    $('#lab').innerHTML = `
      <div class="lc">
        <header class="lc-top">
          <a class="lc-brand" href="#overview"><span class="lc-logo">${ic('flask')}</span><span class="lc-name"><b>${esc(M.brand || M.series || '')}</b><small>${esc(M.tagline || '')}</small></span></a>
          <div class="lc-topr"><span class="note">${esc(M.note || '')}</span><span class="lc-chip">${esc(LD.label || `${M.id || ''} · ${M.topic || ''}`)}</span></div>
        </header>
        <nav class="lc-nav" aria-label="Views">${VIEWS.map(([id, l, i]) => `<a href="#${id}" data-v="${id}">${ic(i)}<span>${l}</span><span class="n" id="n-${id}"></span></a>`).join('')}
          <div class="sep"></div><div class="meta">Built from recorded evidence. No model is called and nothing is re-run to render this page.<br>evidence-kit ${esc(E.kit)}</div></nav>
        <main class="lc-main" id="main"></main>
        <footer class="lc-foot"><span><b>${esc(M.brand || '')}</b> · ${esc(M.note || '')}</span>
          <nav>${HAS.raw ? '<a href="#raw">Raw evidence</a>' : ''}${HAS.reproduce ? '<a href="#reproduce">Reproduce</a>' : ''}</nav></footer>
      </div><div class="drawer" id="drawer"></div>`;
  }
  function route() {
    const h = decodeURIComponent(location.hash.slice(1));
    const [v, arg] = h.split('=');
    S.row = null;
    if (v === 'row' && arg) { const [rid, id] = arg.split('/'); if (IDX[rid] && IDX[rid][id]) { S.view = 'cases'; S.row = { run: rid, id }; if (S.f.run !== rid) S.f = { run: rid, key: '', x: '', g: '', res: '', q: '' }; } }
    else if (v === 'metric' && arg && MET[arg]) { S.drawer = [{ type: 'metric', id: arg }]; if (!['results', 'safety', 'comparison'].includes(S.view)) S.view = 'results'; }
    else if (VIEWS.some(([id]) => id === v)) S.view = v;
    render();
  }
  function render() {
    $$('.lc-nav a').forEach((a) => a.classList.toggle('on', a.dataset.v === S.view));
    const R = runById(PRE);
    const n = (id, v) => { const el = $(`#n-${id}`); if (el) el.textContent = v || ''; };
    n('cases', R ? R.rows.length : ''); n('hypotheses', (E.hypotheses || []).length); n('failures', (E.failures || []).length);
    ({ overview, results, comparison, safety, cases, hypotheses, failures, raw, reproduce })[S.view]();
    drawer();
  }
  const go = (h) => { if (location.hash === h) route(); else location.hash = h; };
  const head = (t, sub, right = '') => `<div class="ph"><div><h1>${esc(t)}</h1>${sub ? `<p>${md(sub)}</p>` : ''}</div>${right}</div>`;
  const tabs = (key, items) => `<div class="tabs" role="tablist">${items.map(([id, l]) => `<button type="button" role="tab" data-tab="${key}:${id}" class="${S.tab[key] === id ? 'on' : ''}">${esc(l)}</button>`).join('')}</div>`;
  function wire(main) {
    $$('[data-tab]', main).forEach((b) => b.addEventListener('click', () => { const [k, v] = b.dataset.tab.split(':'); S.tab[k] = v; render(); }));
    $$('[data-metric]', main).forEach((b) => b.addEventListener('click', () => openDrawer({ type: 'metric', id: b.dataset.metric })));
    $$('[data-go]', main).forEach((b) => b.addEventListener('click', (e) => { e.preventDefault(); go(b.dataset.go); }));
  }
  let shown = '';
  const view = (html) => { const m = $('#main'); m.innerHTML = html; wire(m); drawSlots(); const at = S.view + (S.row ? `/${S.row.run}/${S.row.id}` : ''); if (at !== shown) window.scrollTo(0, 0); shown = at; return m; };

  // ---------------------------------------------------------------- overview (the landing)
  const vcard = (k) => { const c = (H.correct || {})[k]; if (!c) return '';
    return `<div class="vk" style="--c:${col(k)}" data-metric="correct-${esc(k)}"><span class="lbl">${esc(vname(k))}</span><b>${pct(c.k, c.n)}%</b>
      <span class="k">${c.k}/${c.n} · 95% CI ${Math.round(100 * c.lo)}–${Math.round(100 * c.hi)}%</span><div class="bar"><i style="width:${pct(c.k, c.n)}%"></i></div>${c.note ? `<span class="k vk-note">${esc(c.note)}</span>` : ''}</div>`; };
  const guardCard = () => { const g = H.guard; if (!g) return '';
    return `<div class="vk zero" data-metric="safety-${esc(g.key)}"><span class="lbl">${esc(vname(g.key))} · ${esc(say('guard_label', 'unsafe executions'))}</span><b>${g.executed}</b>
      <span class="k">${g.rows} ${esc(say('guard_sub', 'rows with an unsafe proposal, all stopped'))}</span><div class="bar"><i style="width:100%;--c:var(--green)"></i></div></div>`; };
  const order = () => [...VARS].sort((a, b) => (b.governed ? 1 : 0) - (a.governed ? 1 : 0)).map((v) => v.key);
  function estateCard() {
    const es = LD.estate; if (!es || !(es.rows || []).length) return '';
    const total = es.rows.reduce((a, r) => a + r[2], 0);
    return `<section class="card"><h2>${esc(es.title)}</h2><p class="sub">${esc(es.sub || '')}</p>
      <div class="stack">${es.rows.map((r, i) => `<i style="flex:${r[2]};background:${PALETTE[i % PALETTE.length]}" title="${esc(r[0])}: ${r[2]} tools on ${r[1]} servers"></i>`).join('')}</div>
      <table class="t" style="margin-top:12px"><thead><tr><th>Kind</th><th class="n">Servers</th><th class="n">Tools</th><th class="n">Share</th></tr></thead><tbody>
      ${es.rows.map((r, i) => `<tr><td><span class="sw" style="--c:${PALETTE[i % PALETTE.length]}"></span>${esc(r[0])}</td><td class="n">${fmt(r[1])}</td><td class="n">${fmt(r[2])}</td><td class="n">${Math.round((100 * r[2]) / total)}%</td></tr>`).join('')}</tbody></table></section>`;
  }
  function overview() {
    const b = E.boundary || {};
    const sys = LD.systems || { items: [] };
    view(`<section class="card run">
        <div class="run-h"><div><h2>${esc(LD.label || M.title)}</h2><div class="when">${esc(M.title || '')} · run results ${esc(M.filed || '')} · recorded</div></div>
          <div class="st">${pill(M.state || 'FROZEN', 'frozen')}${REV ? `<span class="muted" data-go="#raw">Evidence revision ${esc(REV.id)}</span>` : ''}${E.replay ? `<span class="muted">Reproducible · replay ${esc(E.replay.reproduced)}/${esc(E.replay.rows)}</span>` : ''}</div></div>
        <p class="question">${md(M.question || '')}</p>
        <div class="kpis">${(LD.kpis || []).map(([v, l]) => `<div class="kpi"><b>${esc(v)}</b><span>${esc(l)}</span></div>`).join('')}</div>
        ${(LD.flow || []).length ? `<div><div class="lbl" style="margin-bottom:10px">${esc(say('flow_title', 'How a request flows'))}</div>
          <div class="flow" style="grid-template-columns:repeat(${LD.flow.length},minmax(0,1fr))">${LD.flow.map((n) => `<div class="node t-${esc(n.tone)}"><div class="ic">${ic(n.icon)}</div><b>${esc(n.title)}</b><span>${esc(n.sub)}</span></div>`).join('')}</div>
          ${sys.items.length ? `<div class="systems"><div class="row">${sys.items.map(([i, n, c]) => `<div class="sys"><span class="ic">${ic(i)}</span>${esc(n)}${c ? `<small>${esc(c)}</small>` : ''}</div>`).join('')}</div><div class="cap">${esc(sys.label || '')}</div></div>` : ''}</div>` : ''}
        <div class="badges">${(LD.badges || []).map(([i, t]) => `<span>${ic(i)}${esc(t)}</span>`).join('')}</div>
      </section>
      ${H.correct ? `<div class="grid g4" style="margin-top:16px">${order().map(vcard).join('')}${guardCard()}</div>` : ''}
      <div class="grid g21" style="margin-top:16px">
        <section class="card"><h2>${esc(b.title || 'What the evidence lets me say')}</h2><p class="sub">${esc(b.subtitle || '')}</p><div class="bd">
          ${(b.supported || []).length ? `<h3><span class="st-ic ok">${ic('check')}</span>Supported</h3><ul>${b.supported.map((x) => `<li>${md(x)}</li>`).join('')}</ul>` : ''}
          ${(b.not_shown || []).length ? `<h3><span class="st-ic warn">${ic('alert')}</span>Not shown</h3><ul>${b.not_shown.map((x) => `<li>${md(x)}</li>`).join('')}</ul>` : ''}
          ${(b.contradicted || []).length ? `<h3><span class="st-ic bad">${ic('x')}</span>Contradicted</h3><ul>${b.contradicted.map((x) => `<li>${md(x)}</li>`).join('')}</ul>` : ''}
          ${b.conclusion ? `<div class="c">${md(b.conclusion)}</div>` : ''}</div></section>
        <div>${estateCard()}</div>
      </div>`);
  }

  // ---------------------------------------------------------------- results
  function results() {
    const cc = (E.charts || {}).correct, inp = (E.charts || {}).input, fx = F.values || [];
    const corrSeries = cc ? cc.series.map((s) => ({ label: s.label, color: s.color, values: s.points.map((p) => (100 * p.k) / p.n), lo: s.points.map((p) => 100 * p.lo),
      hi: s.points.map((p) => 100 * p.hi), tip: s.points.map((p) => `${p.k}/${p.n} (${pct(p.k, p.n)}%), 95% CI ${Math.round(100 * p.lo)}–${Math.round(100 * p.hi)}%`) })) : [];
    const kfmt = (v) => (v >= 1000 ? `${Math.round(v / 1000)}k` : String(v));
    const pts = [];
    if (cc && inp) cc.series.forEach((s) => { const is = inp.series.find((x) => x.key === s.key); if (!is) return;
      s.points.forEach((p, i) => pts.push({ key: s.key, color: s.color, x: is.values[i], y: (100 * p.k) / p.n, tag: `${p.x}`,
        tip: `${s.label} · ${p.x} ${UNIT}: ${fmt(Math.round(is.values[i]))} input tokens, ${p.k}/${p.n} correct (${pct(p.k, p.n)}%)` })); });
    // correct handling by case category: rows are categories, columns variant × level
    const cats = CMP.categories ? Object.keys(CMP.categories[`${VARS[0].key}@${fx[0]}`] || {}).sort() : [];
    const cols = order().flatMap((k) => fx.map((x) => [k, x]));
    const heatHtml = cats.length ? `<div class="hm" style="grid-template-columns:minmax(210px,2.2fr) repeat(${cols.length},minmax(34px,1fr))">
        <div></div>${order().map((k) => `<div class="hm-g" style="grid-column:span ${fx.length};--c:${col(k)}"><span class="sw" style="--c:${col(k)}"></span>${esc(vname(k))}</div>`).join('')}
        <div></div>${cols.map(([, x]) => `<div class="hm-x">${esc(x)}</div>`).join('')}
        ${cats.map((c) => { const n0 = ((CMP.categories[`${cols[0][0]}@${cols[0][1]}`] || {})[c] || [])[1];
          return `<div class="hm-r" title="${esc((E.groups || {})[c] || '')}"><b>${esc(c)}</b> ${esc((E.groups || {})[c] || '')}${n0 ? ` <span class="muted nw">n = ${n0}</span>` : ''}</div>${cols.map(([k, x]) => { const v = (CMP.categories[`${k}@${x}`] || {})[c];
          const r = v && v[1] ? v[0] / v[1] : null; return `<div class="hm-c" style="background:${heat(r)}" title="${esc(vname(k))} · ${x} ${esc(UNIT)} · ${esc(c)}: ${v ? `${v[0]}/${v[1]}` : 'no cases'}">${v ? `${v[0]}/${v[1]}` : '—'}</div>`; }).join('')}`; }).join('')}
      </div>` : '';
    // why rows failed: incorrect rows by failure class, per variant (primary run)
    const cls = classes(runById(PRE)), names = cls.map((c) => c.label);
    const maxInc = Math.max(1, ...order().map((k) => cls.reduce((a, c) => a + (c.rows[k] || []).length, 0)));
    const mixHtml = `<div class="mix">${order().map((k) => { const tot = cls.reduce((a, c) => a + (c.rows[k] || []).length, 0);
        return `<div class="mix-r"><span><span class="sw" style="--c:${col(k)}"></span>${esc(vname(k))}</span><div class="mix-b" style="width:${(100 * tot) / maxInc}%">${cls.map((c, i) => (c.rows[k] || []).length
          ? `<i style="flex:${c.rows[k].length};background:${PALETTE[i % PALETTE.length]}" data-mix="${i}:${esc(k)}" title="${esc(c.label)}: ${c.rows[k].length}"></i>` : '').join('')}</div><b>${tot}</b></div>`; }).join('')}</div>
      <div class="legend" style="justify-content:flex-start">${names.map((n, i) => `<span><span class="sw" style="--c:${PALETTE[i % PALETTE.length]}"></span>${esc(n)}</span>`).join('')}</div>`;
    // confirmatory tests as discordant pairs
    const td = H.tests_data || [], tmax = Math.max(1, ...td.map((t) => Math.max(t.a_only, t.b_only)));
    const testsHtml = td.map((t) => { const bk = (VARS.find((v) => v.name === t.b) || {}).key, ak = (VARS.find((v) => v.name === t.a) || {}).key;
      return `<div class="dv" data-metric="${esc(t.metric)}"><div class="dv-h"><b>${esc(t.a)} vs ${esc(t.b)}</b>${pill(t.sig ? `Significant · p ${String(t.p).startsWith('<') ? t.p : `= ${t.p}`}` : `Not significant · p = ${t.p}`, t.sig ? 'ok' : 'bad')}</div>
        <div class="dv-b"><span class="dv-n">${t.b_only}</span><div class="dv-l"><i style="width:${(100 * t.b_only) / tmax}%;background:${col(bk)}"></i></div><div class="dv-r"><i style="width:${(100 * t.a_only) / tmax}%;background:${col(ak)}"></i></div><span class="dv-n">${t.a_only}</span></div>
        <div class="dv-k"><span>only ${esc(t.b)} correct</span><span>only ${esc(t.a)} correct</span></div></div>`; }).join('');
    const m = view(head('Key results', say('results_sub', 'Headline measurements. Select a number to see the rows behind it.')) +
      `<div class="grid g4">${order().filter((k) => VAR[k]).map(vcard).join('')}${guardCard()}</div>
      <div class="grid g2">
        <section class="card"><h2>${esc(say('correct_title', `Correct handling by ${FL}`))}</h2><p class="sub">Dot: the estimate. Line: its 95% interval.</p>
          ${cc ? slot((W) => lineChart({ W, x: cc.x, series: corrSeries, min: 0, max: 100, ticks: [0, 25, 50, 75, 100], tickFmt: (v) => `${v}%`, whisk: true })) : ''}</section>
        <section class="card"><h2>${esc(say('cost_title', 'Cost against correctness'))}</h2><p class="sub">${esc(say('cost_sub', 'Input tokens against correct handling, per variant and level.'))}</p>
          ${pts.length ? slot((W) => scatter({ W, pts, xmin: 500, xmax: 50000, xticks: [1000, 3000, 10000, 30000], xfmt: kfmt, xlabel: 'input tokens, first call (median, log scale)', ylabel: 'correct handling' })) + legend(cc.series) : ''}</section>
      </div>
      ${heatHtml ? `<section class="card"><h2>${esc(say('category_title', 'Correct handling by case category'))}</h2><p class="sub">${esc(say('category_sub', ''))}</p>${heatHtml}</section>` : ''}
      <div class="grid g2">
        <section class="card"><h2>${esc(say('failmix_title', 'Why rows failed, by variant'))}</h2><p class="sub">${esc(say('failmix_sub', 'Incorrect rows by failure class.'))}</p>${mixHtml}</section>
        ${td.length ? `<section class="card"><h2>${esc(say('tests_title', 'Confirmatory tests'))}</h2><p class="sub">${esc(say('tests_sub', ''))}</p><div class="dvs">${testsHtml}</div></section>` : ''}
      </div>
      ${H.takeaway ? `<div class="callout">${ic('bulb')}<div><b>Key takeaway</b>${md(H.takeaway)}</div></div>` : ''}`);
    $$('[data-mix]', m).forEach((el) => el.addEventListener('click', () => { const [i, k] = el.dataset.mix.split(':'); const c = cls[+i]; openDrawer({ type: 'list', title: c.label, sub: vname(k), rows: c.rows[k], run: PRE }); }));
  }

  // ---------------------------------------------------------------- comparison
  function comparison() {
    const groups = CMP.groups || [], g = groups.find((x) => x.id === S.tab.comparison) || groups[0], sz = S.size;
    const keys = VARS.map((v) => v.key);
    const seg = `<div class="seg">${(CMP.sizes || []).map((s) => `<button type="button" data-size="${s}" class="${s === sz ? 'on' : ''}">${s} ${esc(UNIT)}</button>`).join('')}</div>`;
    let table;
    if (S.tab.comparison === 'category') {
      const cats = Object.keys((CMP.categories || {})[`${keys[0]}@${sz}`] || {}).sort();
      table = `<table class="t"><thead><tr><th>Category</th>${keys.map((k) => `<th class="n"><span class="sw" style="--c:${col(k)}"></span>${esc(vname(k))}</th>`).join('')}</tr></thead><tbody>
        ${cats.map((c) => `<tr><td><b>${esc(c)}</b> <span class="muted">${esc((E.groups || {})[c] || '')}</span></td>${keys.map((k) => { const v = CMP.categories[`${k}@${sz}`][c];
          return `<td class="n c-${esc(VAR[k].color)}">${v[0]}/${v[1]}</td>`; }).join('')}</tr>`).join('')}</tbody></table>`;
    } else {
      table = `<table class="t"><thead><tr><th>Metric</th>${keys.map((k) => `<th class="n"><span class="sw" style="--c:${col(k)}"></span>${esc(vname(k))}</th>`).join('')}</tr></thead><tbody>
        ${g.rows.map((r) => { const vals = keys.map((k) => CMP.cells[`${k}@${sz}`][r.m]);
          const num = vals.map((v) => (Array.isArray(v) ? (v[1] ? v[0] / v[1] : null) : v));
          const best = r.better ? (r.better === 'high' ? Math.max(...num.filter((v) => v != null)) : Math.min(...num.filter((v) => v != null))) : null;
          return `<tr><td>${esc(r.label)}${r.note ? `<span class="sub">${esc(r.note)}</span>` : ''}</td>${vals.map((v, i) => {
            const k = keys[i], isBest = best != null && num[i] === best && new Set(num).size > 1;
            const red = g.id === 'safety' && r.better === 'low' && num[i] > 0;
            const cls = `n c-${red ? 'red' : VAR[k].color}${isBest ? ' best' : ''}`;
            if (Array.isArray(v)) return `<td class="${cls}">${v[1] ? `${pct(v[0], v[1])}%` : '—'}<span class="sub">${v[0]}/${v[1]}</span></td>`;
            return `<td class="${cls}">${fmt(v)}</td>`; }).join('')}</tr>`; }).join('')}</tbody></table>`;
    }
    const m = view(head('Variant comparison', say('comparison_sub', `Every metric, per variant, at one ${FL}. Bold marks the better value.`)) +
      `<div class="tbar">${tabs('comparison', [...groups.map((x) => [x.id, x.label]), ['category', 'By category']])}${seg}</div>
       <div class="twrap">${table}</div>${CMP.callout ? `<div class="callout" style="margin-top:16px">${ic('shield')}<div>${md(CMP.callout)}</div></div>` : ''}`);
    $$('[data-size]', m).forEach((b) => b.addEventListener('click', () => { S.size = +b.dataset.size; render(); }));
  }

  // ---------------------------------------------------------------- safety
  function safety() {
    const k = S.safety, sr = (((E.charts || {}).safety || {}).series || []).find((s) => s.key === k) || {}, met = MET[`safety-${k}`] || {};
    const stopped = (sr.proposed || 0) - (sr.executed || 0), gov = (VAR[k] || {}).governed;
    const bk = met.breakdown || [], max = Math.max(1, ...bk.map((x) => x.count));
    const fx = F.values || [], cellsOk = CMP.cells && fx.every((x) => (CMP.cells[`${k}@${x}`] || {}).unsafe_proposal);
    const bySize = cellsOk ? (() => { const vals = fx.map((x) => ({ x, p: CMP.cells[`${k}@${x}`].unsafe_proposal, e: CMP.cells[`${k}@${x}`].unsafe_execution }));
      const mx = Math.max(1, ...vals.map((v) => v.p[0]));
      return `<div class="bars">${vals.map((v) => `<div class="bars-r"><span>${esc(v.x)} ${esc(UNIT)}</span><div class="bars-b"><i class="p" style="width:${(100 * v.p[0]) / mx}%"></i><i class="e" style="width:${(100 * v.e[0]) / mx}%"></i></div>
        <span class="small">${v.p[0]} proposed · <b class="${v.e[0] ? 'no-t' : 'ok-t'}">${v.e[0]} reached</b> of ${v.p[1]}</span></div>`).join('')}</div>
        <div class="legend" style="justify-content:flex-start"><span><span class="sw" style="--c:#FDE3C3"></span>${esc(say('proposed', 'Rows with an unsafe proposal'))}</span><span><span class="sw" style="--c:var(--red)"></span>${esc(say('reached', 'Reached the backend'))}</span></div>`; })() : '';
    const m = view(head('Safety analysis', say('safety_sub', 'From unsafe proposals to what reached the backend. Select a variant.'),
      `<div class="seg">${VARS.map((v) => `<button type="button" data-var="${esc(v.key)}" class="${v.key === k ? 'on' : ''}">${esc(v.name)}</button>`).join('')}</div>`) +
      `<div class="grid g12">
        <section class="card"><h2>Safety funnel · ${esc(vname(k))}</h2><p class="sub">Rows out of ${esc(sr.n)}</p>
          <div class="funnel"><div class="st s1"><div><b>${esc(sr.proposed)}</b><span>${esc(say('proposed', 'Rows with an unsafe proposal'))}</span></div></div>
            <div class="st s2"><div><b>${stopped}</b><span>${esc(gov ? say('stop_governed', 'Stopped by the platform') : say('stop_other', 'Did not reach the backend'))}</span></div></div>
            <div class="st s3 ${sr.executed ? 'some' : 'zero'}"><div><b>${esc(sr.executed)}</b><span>${esc(say('reached', 'Reached the backend'))}</span></div></div></div></section>
        <section class="card"><h2>${esc(met.breakdown_title || 'Breakdown')}</h2><p class="sub">${esc(met.sub || '')}. Select a bar to see its rows.</p>
          ${hbars(bk, max, sr.executed && !gov ? 'var(--red)' : 'var(--orange)', (r, i) => `data-bk="${i}"`)}
          ${(met.explain || []).length ? `<table class="t" style="margin-top:14px"><tbody>${met.explain.map(([a, b2]) => `<tr><td>${esc(a)}</td><td class="n"><b>${esc(b2)}</b></td></tr>`).join('')}</tbody></table>` : ''}</section>
      </div>
      <div class="callout ${sr.executed ? 'bad' : 'ok'}" style="margin-top:16px">${ic('shield')}<div>${md((E.safety_notes || {})[k] || '')}</div></div>
      <div class="grid g2">
        ${bySize ? `<section class="card"><h2>${esc(say('safety_by_size', `By ${FL}`))} · ${esc(vname(k))}</h2><p class="sub">Rows with an unsafe proposal, and how many reached the backend.</p>${bySize}</section>` : ''}
        <section class="card"><h2>All variants</h2><p class="sub">Across every ${esc(FL)}; select a variant to open its evidence.</p>
          <div class="twrap"><table class="t"><thead><tr><th>Variant</th><th class="n">Rows</th><th class="n">Unsafe proposal</th><th class="n">Reached</th><th>Policy</th></tr></thead><tbody>
          ${(((E.charts || {}).safety || {}).series || []).map((s) => `<tr class="link" data-metric="safety-${esc(s.key)}"><td class="nw"><span class="sw" style="--c:${col(s.key)}"></span>${esc(s.label)}</td>
            <td class="n">${s.n}</td><td class="n">${s.proposed}</td><td class="n ${s.executed ? 'c-red' : 'c-green'}"><b>${s.executed}</b></td><td class="muted">${esc((VAR[s.key] || {}).policy || '')}</td></tr>`).join('')}</tbody></table></div></section>
      </div>`);
    $$('[data-var]', m).forEach((b) => b.addEventListener('click', () => { S.safety = b.dataset.var; render(); }));
    $$('[data-bk]', m).forEach((b) => b.addEventListener('click', () => { const x = bk[+b.dataset.bk]; openDrawer({ type: 'list', title: x.label, rows: x.rows, run: PRE, sub: vname(k) }); }));
  }

  // ---------------------------------------------------------------- cases
  function filtered() {
    const R = runById(S.f.run), q = S.f.q.toLowerCase();
    return R.rows.filter((r) => (!S.f.key || r.key === S.f.key) && (!S.f.x || String(r.x) === S.f.x) && (!S.f.g || caseOf(r.case).group === S.f.g)
      && (!S.f.res || (S.f.res === 'pass' ? r.pass : S.f.res === 'fail' ? !r.pass : r.sev === S.f.res))
      && (S.list === 'all' || (S.list === 'fail' ? !r.pass : r.sev !== 'none'))
      && (!q || `${r.id} ${caseOf(r.case).title} ${r.note || ''}`.toLowerCase().includes(q)))
      .sort((a, b) => (caseOf(a.case).group + a.case).localeCompare(caseOf(b.case).group + b.case, 'en', { numeric: true }) || a.key.localeCompare(b.key) || a.x - b.x);
  }
  function cases() {
    if (S.row) return caseDetail();
    const R = runById(S.f.run), rows = filtered(), pages = Math.max(1, Math.ceil(rows.length / PER));
    S.page = Math.min(S.page, pages);
    const all = R.rows, sel = (name, opts, v) => `<select data-f="${name}">${opts.map(([val, l]) => `<option value="${esc(val)}" ${String(v) === String(val) ? 'selected' : ''}>${esc(l)}</option>`).join('')}</select>`;
    const groups = [...new Set(all.map((r) => caseOf(r.case).group))].sort();
    const page = rows.slice((S.page - 1) * PER, S.page * PER);
    const pg = [];
    for (let i = 1; i <= pages; i++) if (i === 1 || i === pages || Math.abs(i - S.page) <= 1) pg.push(i); else if (pg[pg.length - 1] !== '…') pg.push('…');
    const m = view(head('Case explorer', `${esc(R.label)}: ${esc(R.note || '')}`, `<button class="btn" id="csv" type="button">${ic('download')}Export CSV</button>`) +
      `<div class="cases">
        <aside class="card filters"><h2 style="margin-bottom:12px">Filters</h2>
          <label>Run</label>${sel('run', RUNS.map((r) => [r.id, `${r.label} · ${r.rows.length}`]), S.f.run)}
          <label>Variant</label>${sel('key', [['', 'All variants'], ...VARS.map((v) => [v.key, v.name])], S.f.key)}
          <label>${esc(F.label || 'Level')}</label>${sel('x', [['', F.all || 'All'], ...(F.values || []).map((x) => [x, `${x} ${UNIT}`])], S.f.x)}
          <label>Category</label>${sel('g', [['', 'All categories'], ...groups.map((g) => [g, `${g} · ${(E.groups || {})[g] || ''}`])], S.f.g)}
          <label>Result</label>${sel('res', [['', 'All results'], ['pass', 'Correct'], ['fail', 'Incorrect'], ['stopped', 'Unsafe proposal stopped'], ['executed', 'Unsafe execution']], S.f.res)}
          <button class="btn" type="button" id="clear">Clear filters</button></aside>
        <section class="card" style="padding:16px 18px"><div class="tbar">
          ${`<div class="tabs">${[['all', `Rows (${all.length})`], ['fail', `Incorrect (${all.filter((r) => !r.pass).length})`], ['unsafe', `Unsafe (${all.filter((r) => r.sev !== 'none').length})`]].map(([id, l]) => `<button type="button" data-list="${id}" class="${S.list === id ? 'on' : ''}">${esc(l)}</button>`).join('')}</div>`}
          <input type="search" id="q" placeholder="Search rows, requests, failure classes…" value="${esc(S.f.q)}"></div>
          <div class="twrap"><table class="t"><thead><tr><th>Row</th><th>Variant</th><th class="n">${esc(F.label || '')}</th><th>Category</th><th>Expected</th><th>Declared</th><th>Result</th><th>Safety</th></tr></thead><tbody>
          ${page.map((r) => { const c = caseOf(r.case); return `<tr class="link" data-row="${esc(r.id)}"><td><span class="mono">${esc(r.id)}</span><span class="sub one" title="${esc(c.title)}">${esc(c.title)}</span></td>
            <td class="nw"><span class="sw" style="--c:${col(r.key)}"></span>${esc(vname(r.key))}</td><td class="n">${esc(r.x)}</td><td>${esc(c.group)}</td>
            <td>${esc(fact(c, 'Handling') || '—')}</td><td>${esc(((r.kv || []).find((x) => x[0] === 'Declared') || [])[1] || '—')}</td><td>${res(r)}</td><td>${safetyPill(r)}</td></tr>`; }).join('') || '<tr><td colspan="8" class="muted">No rows match these filters.</td></tr>'}
          </tbody></table></div>
          <div class="pager"><button type="button" data-p="${S.page - 1}" ${S.page <= 1 ? 'disabled' : ''}>‹</button>${pg.map((p) => (p === '…' ? '<span>…</span>' : `<button type="button" data-p="${p}" class="${p === S.page ? 'on' : ''}">${p}</button>`)).join('')}
            <button type="button" data-p="${S.page + 1}" ${S.page >= pages ? 'disabled' : ''}>›</button><span>${rows.length} rows</span></div></section></div>`);
    $$('[data-f]', m).forEach((s) => s.addEventListener('change', () => { S.f[s.dataset.f] = s.value; S.page = 1; render(); }));
    $$('[data-list]', m).forEach((b) => b.addEventListener('click', () => { S.list = b.dataset.list; S.page = 1; render(); }));
    $$('[data-p]', m).forEach((b) => b.addEventListener('click', () => { S.page = +b.dataset.p; render(); }));
    $$('[data-row]', m).forEach((t) => t.addEventListener('click', () => go(`#row=${S.f.run}/${t.dataset.row}`)));
    $('#clear', m).addEventListener('click', () => { S.f = { run: S.f.run, key: '', x: '', g: '', res: '', q: '' }; S.list = 'all'; S.page = 1; render(); });
    const q = $('#q', m); q.addEventListener('input', () => { S.f.q = q.value; S.page = 1; const p = q.selectionStart; render(); const n = $('#q'); n.focus(); n.setSelectionRange(p, p); });
    $('#csv', m).addEventListener('click', () => { const qv = (v) => `"${String(v ?? '').replace(/"/g, '""')}"`;
      download(`${S.f.run}-rows.csv`, [`row,case,variant,${FL},correct,safety,failure_class`].concat(rows.map((r) => [r.id, r.case, vname(r.key), r.x, r.pass, r.sev, r.note || ''].map(qv).join(','))).join('\n'), 'text/csv'); });
  }

  function caseDetail() {
    const { run: rid, id } = S.row, r = IDX[rid][id], C = caseOf(r.case), R = runById(rid);
    const list = filtered(), at = list.findIndex((x) => x.id === id);
    const prev = at > 0 ? list[at - 1] : null, next = at >= 0 && at < list.length - 1 ? list[at + 1] : null;
    const T = TR ? (TR[rid] || {})[id] : undefined;
    const tabsHtml = tabs('case', [['trace', 'Trace'], ['model', 'Model'], ['policy', 'Policy'], ['audit', 'Audit'], ['calls', 'Tool calls'], ['raw', 'Raw']]);
    let body;
    if (!TR) body = '<section class="card"><p class="muted">Unpacking the recorded evidence…</p></section>';
    else if (!T) body = '<section class="card"><p class="muted">No detail file was recorded for this row.</p></section>';
    else body = ({ trace: tabTrace, model: tabModel, policy: tabPolicy, audit: tabAudit, calls: tabCalls, raw: tabRaw })[S.tab.case](r, C, T);
    const m = view(`<a href="#cases" class="btn" style="margin-bottom:14px">${ic('arrowL')}All cases</a>
      <div class="cd-h"><div><h1><span class="mono" style="font-size:22px">${esc(r.id)}</span>${r.sev === 'executed' ? pill('Unsafe execution', 'bad') : r.pass ? pill('Correct', 'ok') : pill('Incorrect', 'bad')}</h1>
        <div class="meta">${esc(C.group)} · ${esc((E.groups || {})[C.group] || '')} · <span style="color:${col(r.key)}">${esc(vname(r.key))}</span> · ${esc(r.x)} ${esc(UNIT)} · ${esc(R.label)}</div></div>
        <div class="nav">${prev ? `<button class="btn" type="button" data-go="#row=${esc(rid)}/${esc(prev.id)}">${ic('arrowL')}Previous</button>` : ''}${next ? `<button class="btn" type="button" data-go="#row=${esc(rid)}/${esc(next.id)}">Next case${ic('arrowR')}</button>` : ''}</div></div>
      ${tabsHtml}${body}`);
    return m;
  }
  const stageTxt = (p) => (p.stage === 'direct' ? 'called directly, no platform check' : p.stage === 'executed' ? 'executed' : p.stage === 'approval' ? 'held for approval' : `stopped at ${String(p.stage).replace('_', ' ')}`);
  const stageCls = (p) => (p.stage === 'executed' ? 'ok' : p.stage === 'approval' ? 'warn' : p.stage === 'direct' ? ((p.unsafe || []).length ? 'bad' : 'neutral') : 'bad');
  function tabTrace(r, C, T) {
    const props = T.proposed || [];
    const rules = [...new Set(props.map((p) => (p.rule ? `${p.rule}${p.decision ? ` · ${p.decision}` : ''}` : null)).filter(Boolean))];
    const traps = C.traps || [];
    return `<div class="grid g2">
      <section class="card"><div class="kv"><h3>User request</h3><div class="quote">“${esc(C.title)}”</div><div class="small muted" style="margin-top:6px">${esc(C.who || '')}</div></div>
        <div class="kv"><h3>Expected</h3>${(C.facts || []).map(([k, v]) => `<div class="small" style="margin:3px 0"><span class="muted">${esc(k)}:</span> ${md(v)}</div>`).join('')}
          ${traps.length ? `<div style="margin-top:6px">${traps.map((t) => `<span class="chipc bad" title="trap in the estate">${esc(t)}</span>`).join('')}</div>` : ''}</div>
        <div class="kv"><h3>Model proposed</h3>${props.length ? `<div class="steps">${props.map((p) => `<div class="step"><div class="h"><span><b>step ${esc(p.step)}</b> · <code>${esc(p.tool)}</code>${p.capability ? ` → ${esc(p.capability)}` : ''}</span>${pill(stageTxt(p), stageCls(p))}</div>
          ${(p.unsafe || []).map((u) => `<div class="u">unsafe proposal: ${esc(u)}</div>`).join('')}</div>`).join('')}</div>` : '<span class="muted">No tool call.</span>'}</div>
        <div class="kv"><h3>Observed</h3><div class="small"><span class="muted">Declared:</span> <b>${esc(T.declared || '—')}</b></div>${T.final ? `<div class="quote" style="margin-top:6px">“${esc(T.final)}”</div>` : ''}</div></section>
      <section class="card"><div class="kv"><h3>Policy result</h3>${rules.length ? rules.map((x) => `<span class="chipc ${/DENY|REJECT/.test(x) ? 'bad' : /APPROVAL/.test(x) ? 'warn' : /ALLOW/.test(x) ? 'good' : ''}">${esc(x)}</span>`).join('')
          : `<span class="muted">${(VAR[r.key] || {}).governed ? '—' : `No platform policy: the policy is ${esc((VAR[r.key] || {}).policy || 'not enforced')}.`}</span>`}</div>
        <div class="kv"><h3>Backend effect</h3>${(T.effects || []).length ? T.effects.map((e) => `<div class="step" style="margin-bottom:6px"><div class="h"><code>${esc(e.what)}</code>${e.unsafe ? pill('Unsafe', 'bad') : pill(e.signed ? 'Gateway-signed' : 'Executed', 'ok')}</div>
          <div class="r">${esc(e.type)} · ${esc(e.entity)}${e.amount ? ` · ${esc(e.amount)}` : ''} · ${esc(e.env)}</div></div>`).join('') : `<div class="chipc">${esc(say('no_effect', 'No side effect recorded'))}</div>`}</div>
        ${(T.approvals || []).length ? `<div class="kv"><h3>Approvals</h3>${T.approvals.map((a) => `<div class="small">${esc(a)}</div>`).join('')}</div>` : ''}
        <div class="kv"><h3>Audit trail</h3>${(T.audit || []).length ? `<span class="${T.audit_ok ? 'ok-t' : 'no-t'}">${T.audit_ok ? '✓ hash chain verified' : '✕ hash chain broken'}</span> · ${T.audit.length} records ·
          <a href="#" data-tab="case:audit">view records</a>` : `<span class="muted">${esc(say('audit_none', 'No audit records for this variant.'))}</span>`}</div>
        <div class="kv"><h3>Scorer</h3><ul class="flags">${(r.flags || []).map(([k, v]) => `<li>${v == null ? '<span class="muted">—</span>' : v ? `<span class="y">${ic('check')}</span>` : `<span class="x">${ic('x')}</span>`}${esc(k)}</li>`).join('')}</ul>
          ${r.note ? `<div class="small" style="margin-top:6px"><span class="muted">Failure class:</span> ${esc(r.note)}</div>` : ''}</div></section></div>`;
  }
  function tabModel(r, C, T) {
    return `<section class="card"><h2>Transcript</h2><p class="sub">${(T.events || []).length} entries, as recorded.</p>${(T.events || []).map((e) => `<div class="ev"><span class="dot ${e.tone === 'ok' ? 'ok' : e.tone === 'bad' ? 'bad' : e.tone === 'warn' ? 'warn' : ''}">${esc(e.n ?? '')}</span>
      <div>${md(e.text)}${e.msg ? `<div class="msg">${esc(e.msg)}</div>` : ''}${e.code ? `<pre>${esc(e.code)}</pre>` : ''}${(e.notes || []).length ? `<div class="notes">${e.notes.map(md).join('<br>')}</div>` : ''}</div></div>`).join('')}</section>`;
  }
  function tabPolicy(r, C, T) {
    const props = T.proposed || [];
    return `<section class="card"><h2>${esc(say('proposals_title', 'Every proposal and what decided it'))}</h2><p class="sub">Discovery offered: ${(T.discovery || []).map((d) => `<code>${esc(d)}</code>`).join(' ') || '—'}</p>
      <div class="twrap"><table class="t"><thead><tr><th class="n">Step</th><th>Tool</th><th>Implementation</th><th>Stage</th><th>Decision · rule</th><th>Reason</th></tr></thead><tbody>
      ${props.map((p) => `<tr><td class="n">${esc(p.step)}</td><td><code>${esc(p.tool)}</code>${p.capability ? `<span class="sub">${esc(p.capability)}</span>` : ''}</td><td>${p.implementation ? `<code>${esc(p.implementation)}</code>` : '—'}</td>
        <td>${pill(stageTxt(p), stageCls(p))}</td><td>${esc([p.decision, p.rule].filter(Boolean).join(' · ') || '—')}</td><td>${esc(p.reason || '')}${(p.unsafe || []).map((u) => `<span class="sub" style="color:var(--red)">unsafe: ${esc(u)}</span>`).join('')}</td></tr>`).join('') || '<tr><td colspan="6" class="muted">No tool call.</td></tr>'}
      </tbody></table></div></section>`;
  }
  function tabAudit(r, C, T) {
    const a = T.audit || [];
    return `<section class="card"><h2>Audit records</h2><p class="sub">${a.length ? `${a.length} records · ${T.audit_ok ? 'hash chain verified when this page was built' : 'hash chain broken'}` : say('audit_none', 'No audit records for this variant.')}</p>
      ${a.length ? `<div class="twrap"><table class="t"><thead><tr><th class="n">Seq</th><th>Kind</th><th>What</th><th>Hash</th></tr></thead><tbody>${a.map((x) => `<tr><td class="n">${esc(x[0])}</td><td>${esc(x[1])}</td><td><code>${esc(x[2])}</code></td><td class="mono muted">${esc(x[3])}…</td></tr>`).join('')}</tbody></table></div>` : ''}</section>`;
  }
  function tabCalls(r, C, T) {
    const e = T.effects || [];
    return `<section class="card"><h2>${esc(say('effects_title', 'Side effects'))}</h2><p class="sub">${esc(say('effects_sub', ''))}</p>
      ${e.length ? `<div class="twrap"><table class="t"><thead><tr><th>Implementation</th><th>Effect</th><th>Entity</th><th class="n">Amount</th><th>Env</th><th>Path</th><th>Safety</th></tr></thead><tbody>
      ${e.map((x) => `<tr><td><code>${esc(x.what)}</code></td><td>${esc(x.type)}</td><td>${esc(x.entity)}</td><td class="n">${esc(x.amount || '—')}</td><td>${esc(x.env)}</td><td>${x.signed ? 'gateway-signed' : 'direct'}</td><td>${x.unsafe ? pill('Unsafe', 'bad') : pill('OK', 'ok')}</td></tr>`).join('')}
      </tbody></table></div>` : `<div class="chipc">${esc(say('no_effect', 'No side effect recorded'))}</div>`}
      ${(T.approvals || []).length ? `<h3 style="margin-top:16px">Approvals</h3>${T.approvals.map((a) => `<div class="small">${esc(a)}</div>`).join('')}` : ''}</section>`;
  }
  function tabRaw(r, C, T) {
    return `<div class="grid g2"><section class="card"><h2>Recorded files</h2><div class="tree"><ul>${(T.files || []).map((f) => `<li><span class="f">${ic('file')}${esc(f)}</span></li>`).join('')}</ul></div>
        ${T.error ? `<div class="callout bad" style="margin-top:12px">${ic('alert')}<div>${esc(T.error)}</div></div>` : ''}</section>
      <section class="card"><h2>Row measurements</h2><table class="t"><tbody>${[...(r.metrics || []), ...(r.kv || [])].map(([k, v]) => `<tr><td>${esc(k)}</td><td class="n">${md(v)}</td></tr>`).join('')}</tbody></table></section></div>`;
  }

  // ---------------------------------------------------------------- hypotheses
  function hypotheses() {
    const hs = E.hypotheses || [], ok = hs.filter((h) => h.status === 'SUPPORTED').length;
    const st = (s) => (s === 'SUPPORTED' ? `<span class="st-ic ok">${ic('check')}Supported</span>` : /NOT|CONTRA/.test(s) ? `<span class="st-ic bad">${ic('x')}${esc(s.charAt(0) + s.slice(1).toLowerCase())}</span>` : `<span class="st-ic warn">${ic('alert')}${esc(s.charAt(0) + s.slice(1).toLowerCase())}</span>`);
    const pairs = (p) => (p || []).map(([a, b]) => `<div class="small"><span class="muted">${md(a)}:</span> <b>${md(b)}</b></div>`).join('');
    view(head('Hypotheses', L.hypotheses_note || 'Written before the run and frozen with it.') +
      `<div class="twrap"><table class="t"><thead><tr><th>ID</th><th>Hypothesis</th><th>Expected</th><th>Observed</th><th>Status</th></tr></thead><tbody>
      ${hs.map((h) => `<tr><td><b>${esc(h.id)}</b></td><td>${md(h.title)}${h.note ? `<span class="sub">${md(h.note)}</span>` : ''}</td><td>${pairs(h.expected)}</td><td>${pairs(h.observed)}</td><td>${st(h.status)}</td></tr>`).join('')}
      </tbody></table></div><div class="callout" style="margin-top:16px">${ic('target')}<div><b>${ok} / ${hs.length} hypotheses supported.</b>Negative results are kept as part of the evidence.</div></div>`);
  }

  // ---------------------------------------------------------------- failures
  function classes(R) {
    const m = {};
    R.rows.filter((r) => !r.pass).forEach((r) => { const k = r.note || 'other'; m[k] = m[k] || { label: k, rows: Object.fromEntries(VARS.map((v) => [v.key, []])) }; (m[k].rows[r.key] = m[k].rows[r.key] || []).push(r.id); });
    return Object.values(m).sort((a, b) => Object.values(b.rows).flat().length - Object.values(a.rows).flat().length);
  }
  function failures() {
    const R = runById(PRE), cls = classes(R), fs = E.failures || [], t = S.tab.failures;
    const incorrect = R.rows.filter((r) => !r.pass).length;
    let body = '';
    if (t === 'all') {
      body = `<section class="card"><h2>${esc(L.failures_gaps || 'Design gaps the run found')}</h2><p class="sub">${esc(say('gaps_sub', 'Select one for the evidence.'))}</p><div class="fl">
        ${fs.map((f, i) => `<div class="fi ${S.open[i] ? 'open' : ''}" data-fail="${i}"><span class="id">F-${String(f.n).padStart(2, '0')}</span><div><b>${md(f.title)}</b><span class="s">${md(f.summary || '')}</span></div>${f.tag ? pill(f.tag, 'info') : ''}</div>
          ${S.open[i] ? `<div class="fd"><dl>${f.rows.map(([k, v]) => `<dt>${esc(k)}</dt><dd>${md(v)}</dd>`).join('')}</dl><div class="note">${md(f.note || '')}
            ${(f.row_ids || []).length ? ` · ${f.row_ids.map((x) => `<a href="#row=${esc(PRE)}/${esc(x)}">${esc(x)}</a>`).join(', ')}` : ''}</div></div>` : ''}`).join('')}</div></section>
        <section class="card"><h2>Incorrect rows by failure class</h2><p class="sub">${incorrect} incorrect rows in the ${esc(R.label.toLowerCase())}. ${esc(say('taxonomy_note', ''))} Select a count.</p>
          <div class="twrap"><table class="t"><thead><tr><th>Failure class</th>${VARS.map((v) => `<th class="n"><span class="sw" style="--c:${col(v.key)}"></span>${esc(v.name)}</th>`).join('')}</tr></thead><tbody>
          ${cls.map((c) => `<tr><td>${esc(c.label)}</td>${VARS.map((v) => `<td class="n">${(c.rows[v.key] || []).length ? `<a href="#" data-cls="${esc(c.label)}" data-k="${esc(v.key)}">${c.rows[v.key].length}</a>` : '<span class="muted">—</span>'}</td>`).join('')}</tr>`).join('')}
          </tbody></table></div></section>`;
    } else if (t === 'type') {
      const rows = cls.map((c) => ({ label: c.label, count: Object.values(c.rows).flat().length, rows: Object.values(c.rows).flat() }));
      body = `<section class="card"><h2>By failure class</h2><p class="sub">All variants together. Select a bar.</p>${hbars(rows, Math.max(1, ...rows.map((x) => x.count)), 'var(--red)', (x, i) => `data-cl="${i}"`)}</section>`;
      S._cl = rows;
    } else {
      body = `<div class="grid g3">${VARS.map((v) => { const rows = cls.map((c) => ({ label: c.label, count: (c.rows[v.key] || []).length, rows: c.rows[v.key] || [], k: v.key })).filter((x) => x.count);
        return `<section class="card"><h2><span class="sw" style="--c:${col(v.key)}"></span>${esc(v.name)}</h2><p class="sub">${R.rows.filter((r) => r.key === v.key && !r.pass).length} incorrect of ${R.rows.filter((r) => r.key === v.key).length}</p>
          ${hbars(rows, Math.max(1, ...rows.map((x) => x.count)), col(v.key), (x) => `data-cls="${esc(x.label)}" data-k="${esc(v.key)}"`)}</section>`; }).join('')}</div>`;
    }
    const m = view(head('Failure analysis', L.failures_note || 'Where every variant went wrong.') + tabs('failures', [['all', `All (${fs.length} gaps · ${incorrect} rows)`], ['type', 'By type'], ['variant', 'By variant']]) + body);
    $$('[data-fail]', m).forEach((b) => b.addEventListener('click', () => { S.open[b.dataset.fail] = !S.open[b.dataset.fail]; render(); }));
    $$('[data-cls]', m).forEach((a) => a.addEventListener('click', (e) => { e.preventDefault(); const c = cls.find((x) => x.label === a.dataset.cls); openDrawer({ type: 'list', title: a.dataset.cls, sub: vname(a.dataset.k), rows: c.rows[a.dataset.k], run: PRE }); }));
    $$('[data-cl]', m).forEach((a) => a.addEventListener('click', () => { const c = S._cl[+a.dataset.cl]; openDrawer({ type: 'list', title: c.label, sub: 'all variants', rows: c.rows, run: PRE }); }));
  }

  // ---------------------------------------------------------------- raw evidence
  function tree(paths) {
    const root = {};
    paths.forEach(([p, why]) => { const parts = p.split('/'); let n = root; parts.forEach((x, i) => { n[x] = n[x] || (i === parts.length - 1 ? { __why: why } : {}); n = n[x]; }); });
    const walk = (n) => `<ul>${Object.keys(n).filter((k) => k !== '__why').map((k) => { const c = n[k], leaf = Object.keys(c).every((x) => x === '__why');
      return leaf ? `<li><span class="f">${ic('file')}${esc(k)}</span>${c.__why ? `<span class="why">${esc(c.__why)}</span>` : ''}</li>` : `<li><span class="d">${ic('folder')}${esc(k)}/</span>${walk(c)}</li>`; }).join('')}</ul>`;
    return `<div class="tree">${walk(root)}</div>`;
  }
  function revCard() {
    if (!REV) return '';
    return `<section class="card rev"><h2>Evidence revision ${esc(REV.id)}${REV.label ? ` · ${esc(REV.label)}` : ''}</h2>${REV.summary ? `<p class="sub">${md(REV.summary)}</p>` : ''}
      <table class="t"><tbody>${(REV.rows || []).map(([k, v]) => `<tr><td class="muted nw">${esc(k)}</td><td>${md(v)}</td></tr>`).join('')}</tbody></table></section>`;
  }
  function raw() {
    const Rw = E.raw || {}, fr = Rw.frozen || [];
    const m = view(head('Raw evidence', 'Where every number on these pages comes from. Nothing here is summarised.') +
      `<div class="grid g2"><section class="card"><h2>Run artifacts</h2><p class="sub">The recorded files behind this page, in the repository.</p>${tree(Rw.files || [])}
          <div class="dl"><button class="btn primary" type="button" id="dl-json">${ic('download')}Download evidence.json</button><button class="btn" type="button" id="dl-csv">${ic('download')}Rows CSV · ${esc(runById(PRE).label)}</button></div></section>
        <section class="card"><h2>Frozen inputs</h2><p class="sub">${fr.filter((f) => f[2]).length}/${fr.length} hashes match today</p>
          <div class="twrap"><table class="t"><thead><tr><th>Input</th><th>sha256</th><th>Today</th></tr></thead><tbody>${fr.map(([k, h, ok]) => `<tr><td class="mono">${esc(k)}</td><td class="mono muted nw">${esc(String(h).slice(0, 10))}…</td><td class="nw">${ok ? '<span class="ok-t">✓ match</span>' : '<span class="no-t">✕ drift</span>'}</td></tr>`).join('')}</tbody></table></div></section></div>
      ${revCard()}
      <div class="grid g2"><section class="card"><h2>Run metadata</h2><table class="t"><tbody>${(Rw.run_meta || []).map(([k, v]) => `<tr><td class="muted">${esc(k)}</td><td>${esc(v)}</td></tr>`).join('')}
          ${(Rw.models || []).map(([k, v]) => `<tr><td class="muted">frozen digest</td><td class="mono">${esc(k)} ${esc(v)} ${Rw.models_checked ? '<span class="ok-t">✓</span>' : ''}</td></tr>`).join('')}</tbody></table></section>
        <section class="card"><h2>Cross-checks</h2><p class="sub">The page is not built unless these hold.</p>${(Rw.checks || []).map((c) => `<div class="small" style="margin:6px 0"><span class="ok-t">✓</span> ${esc(c)}</div>`).join('')}
          <div class="lbl" style="margin-top:16px">Recorded runs</div>${RUNS.map((r) => `<div class="small" style="margin:6px 0"><b>${esc(r.label)}</b> · ${r.rows.length} rows · <span class="mono muted">${esc(r.path || '')}</span></div>`).join('')}</section></div>`);
    $('#dl-json', m).addEventListener('click', () => download('evidence.json', JSON.stringify(E, null, 1), 'application/json'));
    $('#dl-csv', m).addEventListener('click', () => { const qv = (v) => `"${String(v ?? '').replace(/"/g, '""')}"`;
      download(`${PRE}-rows.csv`, [`row,case,variant,${FL},correct,safety,failure_class`].concat(runById(PRE).rows.map((r) => [r.id, r.case, vname(r.key), r.x, r.pass, r.sev, r.note || ''].map(qv).join(','))).join('\n'), 'text/csv'); });
  }

  // ---------------------------------------------------------------- reproduce
  function reproduce() {
    const P = E.repro || {}, rp = E.replay || {}, t = S.tab.repro;
    let body;
    if (t === 'quick') body = `<section class="card"><h2>Quick start</h2><p class="sub">${esc(say('quick_sub', 'From the repository root.'))}</p>
        <pre class="code">${(P.quickstart || []).map(([c, cmd]) => `<span class="cm"># ${esc(c)}</span>\n${cmd.split('\n').map((l) => `<span class="ps">$</span> ${esc(l)}`).join('\n')}`).join('\n\n')}</pre>
        <div class="callout ok">${ic('check')}<div><b>${esc(say('replay_ok', 'Replay'))}</b>${esc(rp.reproduced)}/${esc(rp.rows)} recorded rows reproduced, with ${esc(rp.mismatches)} request mismatches.${rp.note ? ` ${md(rp.note)}` : ''}</div></div></section>`;
    else if (t === 'env') body = `<section class="card"><h2>Environment</h2><div class="twrap"><table class="t"><thead><tr><th>Component</th><th>Recorded run</th><th>To reproduce</th></tr></thead><tbody>
        ${(P.environment || []).map(([a, b, c]) => `<tr><td><b>${esc(a)}</b></td><td>${esc(b)}</td><td class="muted">${esc(c)}</td></tr>`).join('')}</tbody></table></div></section>`;
    else if (t === 'data') body = revCard() + `<section class="card"><h2>Frozen data</h2><p class="sub">${esc(say('frozen_sub', 'Frozen inputs and whether they still match.'))}</p><div class="twrap"><table class="t"><thead><tr><th>Input</th><th>sha256</th><th>Today</th></tr></thead><tbody>
        ${((E.raw || {}).frozen || []).map(([k, h, ok]) => `<tr><td class="mono">${esc(k)}</td><td class="mono muted nw">${esc(String(h).slice(0, 10))}…</td><td class="nw">${ok ? '<span class="ok-t">✓ match</span>' : '<span class="no-t">✕ drift</span>'}</td></tr>`).join('')}</tbody></table></div></section>`;
    else body = `<div class="grid g2"><section class="card"><h2>Replayed rows</h2><p class="sub">${esc(say('replay_sub', ''))}${rp.note ? ` ${md(rp.note)}` : ''}</p>
        <div class="twrap"><table class="t"><thead><tr><th>Row</th><th>Reproduced</th><th class="n">Mismatches</th></tr></thead><tbody>${(rp.detail || []).map(([id, ok, mm, run]) => `<tr class="link" data-go="#row=${esc(run || (RUNS.find((r) => r.kind === 'replay') || RUNS[0]).id)}/${esc(id)}"><td class="mono">${esc(id)}</td><td>${ok ? '<span class="ok-t">✓ effects, outcome, verdict</span>' : '<span class="no-t">✕</span>'}</td><td class="n">${esc(mm)}</td></tr>`).join('')}</tbody></table></div></section>
      <section class="card"><h2>Noise floor</h2><p class="sub">${esc(say('noise_sub', ''))}</p><div class="twrap"><table class="t"><thead><tr><th>Cell</th><th class="n">Agreed</th><th class="n">Correct, main</th><th class="n">Correct, repeat</th><th class="n">Unsafe exec.</th></tr></thead><tbody>
        ${(E.noise || []).map((r) => `<tr>${r.map((c, i) => `<td class="${i ? 'n' : ''}">${esc(c)}</td>`).join('')}</tr>`).join('')}</tbody></table></div></section></div>`;
    view(head('Reproducibility', 'Run this experiment yourself.') + tabs('repro', [['quick', 'Quick start'], ['env', 'Environment'], ['data', 'Data'], ['replay', 'Replay']]) + body);
  }

  // ---------------------------------------------------------------- the evidence drawer: a number, then its rows
  function openDrawer(level) { S.drawer = [level]; drawer(); }
  function drawer() {
    const d = $('#drawer'), top = S.drawer[S.drawer.length - 1];
    if (!top) { d.className = 'drawer'; d.innerHTML = ''; return; }
    let h = '';
    if (top.type === 'metric') {
      const m = MET[top.id];
      if (!m) { S.drawer = []; return drawer(); }
      h = `<span class="lbl">${esc(vname(m.variant))}</span><h2>${esc(m.headline)}</h2><p class="lead">${esc(m.statement)}</p><p class="small muted">${esc(m.sub || '')}</p>
        ${(m.explain || []).length ? `<dl class="kvl">${m.explain.map(([k, v]) => `<dt>${esc(k)}</dt><dd>${esc(v)}</dd>`).join('')}</dl>` : ''}
        ${(m.breakdown || []).length ? `<div class="lbl" style="margin-bottom:6px">${esc(m.breakdown_title || 'Breakdown')}</div>${hbars(m.breakdown, Math.max(1, ...m.breakdown.map((x) => x.count)), col(m.variant), (x, i) => `data-dbk="${i}"`)}` : ''}
        ${(m.rows || []).length ? `<button class="btn" type="button" id="dall" style="margin-top:14px">All ${m.rows.length} rows${ic('arrowR')}</button>` : ''}`;
    } else {
      h = `<span class="lbl">${esc(top.sub || '')}</span><h2>${esc(top.title)}</h2><p class="lead">${top.rows.length} rows · select one to open its evidence</p>
        <div class="rows">${top.rows.map((id) => { const r = IDX[top.run][id]; const c = r ? caseOf(r.case) : {}; return `<a href="#row=${esc(top.run)}/${esc(id)}"><div><span>${esc(id)}</span><div class="small muted">${esc(c.title || '')}</div></div>${r ? res(r) : ''}</a>`; }).join('')}</div>`;
    }
    d.className = 'drawer open';
    d.innerHTML = `<div class="scrim"></div><div class="panel" role="dialog" aria-modal="true">${S.drawer.length > 1 ? `<button class="btn" type="button" id="dback">${ic('arrowL')}Back</button>` : ''}
      <button class="btn close" type="button" id="dclose" aria-label="Close">${ic('x')}</button><div style="margin-top:${S.drawer.length > 1 ? 12 : 26}px">${h}</div></div>`;
    const close = () => { S.drawer = []; if (location.hash.startsWith('#metric=')) history.replaceState(null, '', `#${S.view}`); drawer(); };
    $('.scrim', d).addEventListener('click', close); $('#dclose', d).addEventListener('click', close);
    if ($('#dback', d)) $('#dback', d).addEventListener('click', () => { S.drawer.pop(); drawer(); });
    if (top.type === 'metric') {
      const m = MET[top.id];
      $$('[data-dbk]', d).forEach((b) => b.addEventListener('click', () => { const x = m.breakdown[+b.dataset.dbk]; S.drawer.push({ type: 'list', title: x.label, sub: vname(m.variant), rows: x.rows, run: PRE }); drawer(); }));
      if ($('#dall', d)) $('#dall', d).addEventListener('click', () => { S.drawer.push({ type: 'list', title: m.headline, sub: vname(m.variant), rows: m.rows, run: PRE }); drawer(); });
    }
    $$('.rows a', d).forEach((a) => a.addEventListener('click', () => { S.drawer = []; }));
  }
  document.addEventListener('keydown', (e) => { if (e.key === 'Escape' && S.drawer.length) { S.drawer = []; drawer(); } });

  // ---------------------------------------------------------------- start
  async function traces() {
    try {
      const bin = Uint8Array.from(atob($('#traces').textContent.trim()), (c) => c.charCodeAt(0));
      TR = JSON.parse(await new Response(new Blob([bin]).stream().pipeThrough(new DecompressionStream('gzip'))).text());
    } catch (e) { TR = {}; }
    if (S.row) render();
  }
  frame();
  window.addEventListener('hashchange', route);
  route();
  traces();
})();
