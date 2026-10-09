/* evidence-kit 5 · Lab Console / Proof Lab.  Pages of view primitives, composed by each learning's spec (learning.toml)
   and filled from its evidence.json: run card, rate cards, claims, composition, line chart, scatter, heatmap, mix,
   paired tests, callout, comparison, funnel, case explorer (with data-driven case tabs), hypotheses, failures,
   artifacts, reproduce, metric grid, table, timeline, distribution, and the Proof Contract v1 views (pae-proof/v1):
   proof hero, execution profile, experiment scorecard, claim trace, integrity, negative control.  Any block can carry a
   provenance footer (prov).  The kit draws; every word that names something in an
   experiment comes from the spec or the data.  Numbers are read, never computed, apart from counts over the rows. */
(() => {
  'use strict';
  const $ = (s, el = document) => el.querySelector(s);
  const $$ = (s, el = document) => [...el.querySelectorAll(s)];
  const E = JSON.parse($('#evidence').textContent);
  const M = E.meta || {}, D = E.dimensions || {}, DS = E.datasets || {}, A = E.artifacts || {};
  const REV = A.revision || null, RP = A.replay || null;
  const VARS = D.variants || [], VAR = Object.fromEntries(VARS.map((v) => [v.key, v]));
  const RUNS = E.runs || [], PRE = RUNS.length ? RUNS[0].id : null;
  const IDX = Object.fromEntries(RUNS.map((r) => [r.id, Object.fromEntries(r.rows.map((x) => [x.id, x]))]));
  const MET = Object.fromEntries((E.metrics || []).map((m) => [m.id, m]));
  const F = D.factor || {}, FL = String(F.label || 'level').toLowerCase(), UNIT = F.unit || '';
  const SEV = D.severity || [{ id: 'none' }], SV = Object.fromEntries(SEV.map((s) => [s.id, s]));
  const RES = D.result || { pass: 'Pass', fail: 'Fail' };
  const PAGES = E.pages || [];
  const blocksOf = (bs) => (bs || []).flatMap((b) => [b, ...(b.type === 'grid' ? blocksOf(b.items) : [])]);
  const findBlock = (type) => { for (const p of PAGES) { const b = blocksOf(p.blocks).find((x) => x.type === type); if (b) return [p, b]; } return [null, null]; };
  const [CE_PAGE, CE] = findBlock('case_explorer'), [ART_PAGE] = findBlock('artifacts'), [, CMPB] = findBlock('comparison'), [, FUN] = findBlock('funnel');
  const CMP = (CMPB && DS[CMPB.data]) || {};
  const PER = 15;
  let TR = null;
  const S = { view: (PAGES[0] || {}).id, row: null, drawer: [], page: 1, list: 'all', size: CMP.default || (F.values || []).slice(-1)[0],
    tab: { comparison: ((CMPB || {}).groups || [{}])[0].id, failures: 'all', repro: 'quick', case: ((E.case_tabs || [])[0] || {}).id },
    safety: (VARS.find((v) => v.governed) || VARS[0] || {}).key, f: { run: PRE, key: '', x: '', g: '', res: '', q: '' }, open: {} };

  // ---------------------------------------------------------------- helpers
  const esc = (v) => String(v ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const md = (s) => esc(s).replace(/`([^`]+)`/g, '<code>$1</code>').replace(/\*\*([^*]+)\*\*/g, '<b>$1</b>').replace(/\*([^*]+)\*/g, '<i>$1</i>');
  const fmt = (n) => (typeof n === 'number' ? (Number.isInteger(n) ? n.toLocaleString('en-US') : n.toLocaleString('en-US', { maximumFractionDigits: 1 })) : esc(n));
  const pct = (k, n) => (n ? Math.round((100 * k) / n) : 0);
  const tpl = (s, v) => String(s ?? '').replace(/\{(\w+)\}/g, (m, k) => (v && v[k] != null ? v[k] : m));  // runtime values: {n}, {name} …
  const col = (k) => `var(--${(VAR[k] || {}).color || 'graphite'})`;
  const vname = (k) => (VAR[k] || {}).name || k;
  const caseOf = (id) => (E.cases || {})[id] || { title: id, group: '', facts: [] };
  const fact = (c, k) => ((c.facts || []).find((f) => f[0] === k) || [])[1];
  const runById = (id) => RUNS.find((r) => r.id === id) || RUNS[0];
  const pill = (t, cls) => `<span class="pill ${cls}">${esc(t)}</span>`;
  const PR = E.proof || {};
  const CHK = Object.fromEntries((PR.checks || []).map((c) => [c.id, c])), EXP = Object.fromEntries((PR.experiments || []).map((x) => [x.id, x]));
  const CLM = Object.fromEntries((PR.claims || []).map((c) => [c.id, c]));
  const STC = { PASS: 'ok', FAIL: 'bad', EXPECTED_FAILURE: 'info', 'N/A': 'neutral', supported: 'ok', contradicted: 'bad', not_established: 'warn', implementation: 'ok', control: 'info', limitation: 'neutral' };
  const RC = { REAL: 'green', SIMULATED: 'blue', RECORDED: 'indigo', GENERATED: 'amber', INJECTED: 'red', ARCHITECTURE: 'grey' };
  const stLabel = (s) => (s === 'N/A' ? s : String(s || '').replace(/_/g, ' ').toLowerCase().replace(/^./, (c) => c.toUpperCase()));
  const stPill = (s) => pill(stLabel(s), STC[s] || 'neutral');
  // 5.1, findings: the status stays the machine verdict; a reader sees whether a FAIL is a reported finding or a broken guarantee
  const FC = { PASS: 'ok', 'EXPECTED FAILURE': 'info', FAIL: 'bad', 'NOT SUPPORTED': 'warn', 'NOT ESTABLISHED': 'warn', 'NOT OBSERVED': 'warn', 'LIMITATION OBSERVED': 'warn' };
  const fdOf = (x) => x.finding || (x.status || x.result) && ({ PASS: 'PASS', EXPECTED_FAILURE: 'EXPECTED FAILURE', FAIL: 'FAIL' })[x.status || x.result] || '';
  const fdCls = (f) => FC[f] || (String(f).includes(' · ') ? 'warn' : 'neutral');
  const fdLabel = (f) => String(f).split(' · ').map((p) => p.toLowerCase().replace(/^./, (c) => c.toUpperCase())).join(' · ');
  const fdPill = (x) => pill(fdLabel(fdOf(x)), fdCls(fdOf(x)));
  const chk = (id) => `<a href="#check=${esc(id)}" class="chk ${esc(fdCls(fdOf(CHK[id] || {})) || '')}" data-chk="${esc(id)}" title="${esc((CHK[id] || {}).description || '')}">${esc(id)}</a>`;
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
    card: '<rect x="2" y="5" width="20" height="14" rx="2"/><path d="M2 10h20"/>', undo: '<path d="M3 12a9 9 0 1 0 3-6.7L3 8"/><path d="M3 3v5h5"/>',
    truck: '<path d="M2 6h12v10H2zM14 9h4l3 3v4h-7"/><circle cx="6.5" cy="18" r="1.8"/><circle cx="17.5" cy="18" r="1.8"/>',
    users: '<circle cx="9" cy="8" r="3.5"/><path d="M2.5 20a6.5 6.5 0 0 1 13 0"/><path d="M16 4.5a3.5 3.5 0 0 1 0 7M21.5 20a6.5 6.5 0 0 0-4-6"/>',
    tag: '<path d="M20.6 13.4 13.4 20.6a2 2 0 0 1-2.8 0L3 13V3h10l7.6 7.6a2 2 0 0 1 0 2.8z"/><path d="M7.5 7.5h.01"/>', book: '<path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20V3H6.5A2.5 2.5 0 0 0 4 5.5z"/><path d="M4 19.5A2.5 2.5 0 0 0 6.5 22H20v-5"/>',
    plug: '<path d="M9 2v6M15 2v6M6 8h12v4a6 6 0 0 1-12 0zM12 18v4"/>', box: '<path d="M21 8 12 3 3 8l9 5z"/><path d="M3 8v8l9 5 9-5V8M12 13v8"/>',
    lock: '<rect x="4" y="11" width="16" height="10" rx="2"/><path d="M8 11V7a4 4 0 0 1 8 0v4"/>', cpu: '<rect x="6" y="6" width="12" height="12" rx="2"/><path d="M9 2v4M15 2v4M9 18v4M15 18v4M2 9h4M2 15h4M18 9h4M18 15h4"/>',
    refresh: '<path d="M3 12a9 9 0 0 1 15.4-6.4L21 8M21 3v5h-5M21 12a9 9 0 0 1-15.4 6.4L3 16M3 21v-5h5"/>', arrowL: '<path d="M19 12H5M12 19l-7-7 7-7"/>',
    arrowR: '<path d="M5 12h14M12 5l7 7-7 7"/>', ext: '<path d="M14 3h7v7M10 14 21 3M19 14v5a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2h5"/>',
    clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>', layers: '<path d="m12 3 9 5-9 5-9-5z"/><path d="m3 13 9 5 9-5"/>',
  };
  const ic = (n) => `<svg class="i" viewBox="0 0 24 24" aria-hidden="true">${I[n] || I.file}</svg>`;
  const res = (r) => (r.pass ? `<span class="res-ok" title="${esc(RES.pass)}">${ic('check')}</span>` : `<span class="res-no" title="${esc(RES.fail)}">${ic('x')}</span>`);
  const sevOf = (r) => SV[r.sev] || SV.none || { id: 'none' };
  const sevPill = (r) => { const s = sevOf(r); return s.label ? pill(s.label, s.tone || 'warn') : '<span class="muted">—</span>'; };
  const top = SEV[SEV.length - 1];  // the most severe level heads a case when it applies
  const download = (name, text, type) => { const a = document.createElement('a'); a.href = URL.createObjectURL(new Blob([text], { type })); a.download = name; document.body.appendChild(a); a.click(); a.remove(); };
  const csvOf = (rows) => { const qv = (v) => `"${String(v ?? '').replace(/"/g, '""')}"`;
    return [tpl((CE || {}).csv_head || 'row,case,variant,{factor},pass,severity,note', { factor: FL })].concat(rows.map((r) => [r.id, r.case, vname(r.key), r.x, r.pass, r.sev, r.note || ''].map(qv).join(','))).join('\n'); };
  const ready = (b) => ({ rate_cards: () => DS[b.data], comparison: () => DS[b.data] && DS[b.data].cells, funnel: () => DS[b.data], case_explorer: () => RUNS.length,
    hypotheses: () => (E.hypotheses || []).length, failures: () => RUNS.length, artifacts: () => Object.keys(A).length, reproduce: () => A.repro || RP || b.quickstart,
    line_chart: () => DS[b.data], scatter: () => DS[b.x] && DS[b.y], heatmap: () => DS[b.data], paired_tests: () => (DS[b.data] || []).length,
    composition: () => DS[b.data] && (DS[b.data].rows || []).length, timeline: () => DS[b.data], distribution: () => DS[b.data], table: () => DS[b.data] || b.rows,
    proof_hero: () => E.proof, profile: () => E.proof && E.proof.profile, scorecard: () => ((E.proof || {}).experiments || []).length,
    claim_trace: () => ((E.proof || {}).claims || []).length, integrity: () => E.proof && E.proof.integrity, control: () => E.proof && E.proof.control }[b.type] || (() => true))();
  const VIEWS = PAGES.filter((p) => blocksOf(p.blocks).some((b) => b.type !== 'head' && b.type !== 'grid' && ready(b)));
  const pageById = (id) => VIEWS.find((p) => p.id === id) || VIEWS[0];

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
    const placed = [];  // level tags, skipped where they would collide with one already drawn
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
  function boxes({ W, series, unit }) {  // distribution: min · quartiles · median · max per series, on one scale
    const l = 170, r = 24, rowh = 38, Hh = rowh * series.length + 34;
    const all = series.flatMap((s) => s.values), lo = Math.min(...all), hi = Math.max(...all), w = W - l - r;
    const X = (v) => l + (hi === lo ? w / 2 : (w * (v - lo)) / (hi - lo));
    const q = (vs, p) => { const s = [...vs].sort((a, b) => a - b), i = (s.length - 1) * p, f = Math.floor(i); return s[f] + (s[Math.min(f + 1, s.length - 1)] - s[f]) * (i - f); };
    let s = `<svg class="ch" width="${W}" height="${Hh}" viewBox="0 0 ${W} ${Hh}" role="img">`;
    series.forEach((se, i) => {
      const y = 16 + i * rowh, c = `var(--${se.color})`, [a, b1, m, b3, z] = [0, 0.25, 0.5, 0.75, 1].map((p) => q(se.values, p));
      s += `<text class="ax" x="0" y="${y + 14}">${esc(se.label)}</text><line class="gl" x1="${X(a)}" x2="${X(z)}" y1="${y + 10}" y2="${y + 10}" stroke="${c}"/>`
        + `<rect x="${X(b1)}" y="${y + 2}" width="${Math.max(2, X(b3) - X(b1))}" height="16" fill="${c}" fill-opacity=".25" stroke="${c}"/><line x1="${X(m)}" x2="${X(m)}" y1="${y}" y2="${y + 20}" stroke="${c}" stroke-width="2.5"><title>${esc(se.label)}: median ${fmt(m)} ${esc(unit || '')}</title></line>`;
    });
    s += `<text class="ax" x="${l}" y="${Hh - 4}">${fmt(lo)} ${esc(unit || '')}</text><text class="ax" x="${W - r}" y="${Hh - 4}" text-anchor="end">${fmt(hi)} ${esc(unit || '')}</text>`;
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
          <a class="lc-brand" href="#${esc((VIEWS[0] || {}).id || '')}"><span class="lc-logo">${ic('flask')}</span><span class="lc-name"><b>${esc(M.brand || M.series || '')}</b><small>${esc(M.tagline || '')}</small></span></a>
          <div class="lc-topr"><span class="note">${esc(M.note || '')}</span><span class="lc-chip">${esc(M.label || `${M.id || ''} · ${M.topic || ''}`)}</span></div>
        </header>
        <nav class="lc-nav" aria-label="Views">${VIEWS.map((p) => `<a href="#${esc(p.id)}" data-v="${esc(p.id)}">${ic(p.icon)}<span>${esc(p.title)}</span><span class="n" id="n-${esc(p.id)}"></span></a>`).join('')}
          <div class="sep"></div><div class="meta">Built from recorded evidence. No model is called and nothing is re-run to render this page.<br>evidence-kit ${esc(E.kit)}</div></nav>
        <main class="lc-main" id="main"></main>
        <footer class="lc-foot"><span><b>${esc(M.brand || '')}</b> · ${esc(M.note || '')}</span>
          <nav>${VIEWS.filter((p) => p.footer).map((p) => `<a href="#${esc(p.id)}">${esc(p.title)}</a>`).join('')}</nav></footer>
      </div><div class="drawer" id="drawer"></div>`;
  }
  function route() {
    const h = decodeURIComponent(location.hash.slice(1));
    const [v, arg] = h.split('=');
    S.row = null;
    if (v === 'row' && arg && CE_PAGE) { const [rid, id] = arg.split('/'); if (IDX[rid] && IDX[rid][id]) { S.view = CE_PAGE.id; S.row = { run: rid, id }; if (S.f.run !== rid) S.f = { run: rid, key: '', x: '', g: '', res: '', q: '' }; } }
    else if (v === 'metric' && arg && MET[arg]) { S.drawer = [{ type: 'metric', id: arg }]; if (!(pageById(S.view) || {}).metrics) S.view = (VIEWS.find((p) => p.metrics) || VIEWS[0]).id; }
    else if (['check', 'experiment', 'claim'].includes(v) && arg) { S.drawer = [{ type: v, id: arg }]; const [pg] = findBlock(v === 'claim' ? 'claim_trace' : 'scorecard'); if (pg && VIEWS.includes(pg)) S.view = pg.id; }
    else if (VIEWS.some((p) => p.id === v)) S.view = v;
    render();
  }
  let W = [];
  function render() {
    $$('.lc-nav a').forEach((a) => a.classList.toggle('on', a.dataset.v === S.view));
    const counts = { rows: (runById(PRE) || { rows: [] }).rows.length, hypotheses: (E.hypotheses || []).length, failures: (E.failures || []).length };
    VIEWS.forEach((p) => { const el = $(`#n-${p.id}`); if (el) el.textContent = p.count ? counts[p.count] || '' : ''; });
    const p = pageById(S.view);
    W = [];
    const html = S.row && p === CE_PAGE ? caseDetail() : (p.blocks || []).map(draw).join('');
    const m = view(html);
    W.forEach((f) => f(m));
    drawer();
  }
  const provHtml = (p) => `<p class="prov"><span class="pb ${esc(String(p.class || '').toLowerCase())}">${esc(p.class || '')}</span>${(p.parts || []).map((x) => `<span>${md(x)}</span>`).join('')}${(p.checks || []).map((c) => chk(c)).join('')}</p>`;
  const withProv = (html, p) => (!p || !html ? html : html.endsWith('</section>') ? `${html.slice(0, -10)}${provHtml(p)}</section>` : html + provHtml(p));
  const draw = (b) => (b.type === 'grid' || ready(b) ? withProv((P[b.type] || (() => ''))(b), b.prov) : '');
  const go = (h) => { if (location.hash === h) route(); else location.hash = h; };
  const head = (t, sub, right = '') => `<div class="ph"><div><h1>${esc(t)}</h1>${sub ? `<p>${md(sub)}</p>` : ''}</div>${right}</div>`;
  const tabs = (key, items) => `<div class="tabs" role="tablist">${items.map(([id, l]) => `<button type="button" role="tab" data-tab="${key}:${id}" class="${S.tab[key] === id ? 'on' : ''}">${esc(l)}</button>`).join('')}</div>`;
  function wire(main) {
    $$('[data-tab]', main).forEach((b) => b.addEventListener('click', (e) => { e.preventDefault(); const [k, v] = b.dataset.tab.split(':'); S.tab[k] = v; render(); }));
    $$('[data-metric]', main).forEach((b) => b.addEventListener('click', () => openDrawer({ type: 'metric', id: b.dataset.metric })));
    $$('[data-go]', main).forEach((b) => b.addEventListener('click', (e) => { e.preventDefault(); go(b.dataset.go); }));
    proofLinks(main, (lv) => openDrawer(lv));
  }
  function proofLinks(el, open) {  // a check, an experiment or a claim opens its drawer (the innermost link wins)
    [['data-chk', 'check'], ['data-exp', 'experiment'], ['data-clm', 'claim']].forEach(([a, t]) => $$(`[${a}]`, el).forEach((x) => x.addEventListener('click', (e) => {
      e.preventDefault(); e.stopPropagation(); open({ type: t, id: x.getAttribute(a) }); })));
  }
  let shown = '';
  const view = (html) => { const m = $('#main'); m.innerHTML = html; wire(m); drawSlots(); const at = S.view + (S.row ? `/${S.row.run}/${S.row.id}` : ''); if (at !== shown) window.scrollTo(0, 0); shown = at; return m; };
  const order = () => [...VARS].sort((a, b) => (b.governed ? 1 : 0) - (a.governed ? 1 : 0)).map((v) => v.key);
  const card = (title, sub, body, extra = '') => `<section class="card"${extra}>${title != null ? `<h2>${esc(title)}</h2>` : ''}${sub != null ? `<p class="sub">${md(sub)}</p>` : ''}${body}</section>`;

  // ---------------------------------------------------------------- primitives
  const P = {};
  P.head = (b) => head(b.title, b.sub);
  P.grid = (b) => `<div class="grid ${esc(b.cls || 'g2')}"${b.style ? ` style="${esc(b.style)}"` : ''}>${(b.items || []).map((it) => (it.wrap ? `<div>${draw(it)}</div>` : draw(it))).join('')}</div>`;
  P.callout = (b) => `<div class="callout${b.tone ? ` ${esc(b.tone)}` : ''}"${b.style ? ` style="${esc(b.style)}"` : ''}>${ic(b.icon || 'bulb')}<div>${b.title ? `<b>${esc(b.title)}</b>` : ''}${md(b.text)}</div></div>`;

  P.run_card = (b) => {
    const sys = DS[b.systems] || { items: [] }, flow = b.flow || [];
    return `<section class="card run">
        <div class="run-h"><div><h2>${esc(M.label || M.title)}</h2><div class="when">${esc(M.title || '')} · run results ${esc(M.filed || '')} · recorded</div></div>
          <div class="st">${pill(M.state || 'FROZEN', 'frozen')}${REV && ART_PAGE ? `<span class="muted" data-go="#${esc(ART_PAGE.id)}">Evidence revision ${esc(REV.id)}</span>` : ''}${RP ? `<span class="muted">Reproducible · replay ${esc(RP.reproduced)}/${esc(RP.rows)}</span>` : ''}</div></div>
        <p class="question">${md(M.question || '')}</p>
        <div class="kpis">${(b.kpis || []).map(([v, l]) => `<div class="kpi"><b>${esc(v)}</b><span>${esc(l)}</span></div>`).join('')}</div>
        ${flow.length ? `<div><div class="lbl" style="margin-bottom:10px">${esc(b.flow_title || '')}</div>
          <div class="flow" style="grid-template-columns:repeat(${flow.length},minmax(0,1fr))">${flow.map((n) => `<div class="node t-${esc(n.tone)}"><div class="ic">${ic(n.icon)}</div><b>${esc(n.title)}</b><span>${esc(n.sub)}</span></div>`).join('')}</div>
          ${sys.items.length ? `<div class="systems"><div class="row">${sys.items.map(([i, n, c]) => `<div class="sys"><span class="ic">${ic(i)}</span>${esc(n)}${c ? `<small>${esc(c)}</small>` : ''}</div>`).join('')}</div><div class="cap">${esc(b.systems_label || sys.label || '')}</div></div>` : ''}</div>` : ''}
        <div class="badges">${(b.badges || []).map(([i, t]) => `<span>${ic(i)}${esc(t)}</span>`).join('')}</div>
      </section>`;
  };

  P.rate_cards = (b) => {  // one card per variant (a rate with its interval), then an optional zero-count card
    const H = DS[b.data] || {}, notes = b.notes || {};
    const vcard = (k) => { const c = (H.rates || {})[k]; if (!c) return '';
      return `<div class="vk" style="--c:${col(k)}" data-metric="${esc((b.metric || '') + k)}"><span class="lbl">${esc(vname(k))}</span><b>${pct(c.k, c.n)}%</b>
      <span class="k">${c.k}/${c.n} · 95% CI ${Math.round(100 * c.lo)}–${Math.round(100 * c.hi)}%</span><div class="bar"><i style="width:${pct(c.k, c.n)}%"></i></div>${notes[k] ? `<span class="k vk-note">${esc(notes[k])}</span>` : ''}</div>`; };
    const g = H.zero, zero = g && b.zero ? `<div class="vk zero" data-metric="${esc((b.zero.metric || '') + g.key)}"><span class="lbl">${esc(vname(g.key))} · ${esc(b.zero.label || '')}</span><b>${g.value}</b>
      <span class="k">${g.of} ${esc(b.zero.sub || '')}</span><div class="bar"><i style="width:100%;--c:var(--green)"></i></div></div>` : '';
    return `<div class="grid g4"${b.style ? ` style="${esc(b.style)}"` : ''}>${order().filter((k) => VAR[k]).map(vcard).join('')}${zero}</div>`;
  };

  P.claims = (b) => {
    const c = E.claims || {}, groups = b.groups || [['supported', 'Supported', 'check', 'ok'], ['not_established', 'Not established', 'alert', 'warn'], ['contradicted', 'Contradicted', 'x', 'bad']];
    return card(c.title || '', c.subtitle || '', `<div class="bd">
          ${groups.map(([k, l, i, cls]) => ((c[k] || []).length ? `<h3><span class="st-ic ${cls}">${ic(i)}</span>${esc(l)}</h3><ul>${c[k].map((x) => `<li>${md(x)}</li>`).join('')}</ul>` : '')).join('\n          ')}
          ${c.conclusion ? `<div class="c">${md(c.conclusion)}</div>` : ''}</div>`);
  };

  P.composition = (b) => {  // a whole split into parts: one stacked bar and a table (label, count a, count b, share of b)
    const es = DS[b.data], total = es.rows.reduce((a, r) => a + r[2], 0), [h0, h1, h2, h3] = b.head || ['', '', '', 'Share'];
    return card(b.title, b.sub || '', `
      <div class="stack">${es.rows.map((r, i) => `<i style="flex:${r[2]};background:${PALETTE[i % PALETTE.length]}" title="${esc(tpl(b.tip || '{label}: {b}', { label: r[0], a: r[1], b: r[2] }))}"></i>`).join('')}</div>
      <table class="t" style="margin-top:12px"><thead><tr><th>${esc(h0)}</th><th class="n">${esc(h1)}</th><th class="n">${esc(h2)}</th><th class="n">${esc(h3)}</th></tr></thead><tbody>
      ${es.rows.map((r, i) => `<tr><td><span class="sw" style="--c:${PALETTE[i % PALETTE.length]}"></span>${esc(r[0])}</td><td class="n">${fmt(r[1])}</td><td class="n">${fmt(r[2])}</td><td class="n">${Math.round((100 * r[2]) / total)}%</td></tr>`).join('')}</tbody></table>`);
  };

  P.line_chart = (b) => {  // a rate per variant across the factor's levels, with intervals
    const cc = DS[b.data];
    const series = cc.series.map((s) => ({ label: s.label, color: s.color, values: s.points.map((p) => (100 * p.k) / p.n), lo: s.points.map((p) => 100 * p.lo),
      hi: s.points.map((p) => 100 * p.hi), tip: s.points.map((p) => `${p.k}/${p.n} (${pct(p.k, p.n)}%), 95% CI ${Math.round(100 * p.lo)}–${Math.round(100 * p.hi)}%`) }));
    return card(b.title, b.sub || 'Dot: the estimate. Line: its 95% interval.', `
          ${slot((Wd) => lineChart({ W: Wd, x: cc.x, series, min: 0, max: 100, ticks: [0, 25, 50, 75, 100], tickFmt: (v) => `${v}%`, whisk: true }))}`);
  };

  P.scatter = (b) => {  // one measurement (log x) against a rate (y), per variant and level
    const cc = DS[b.y], inp = DS[b.x], pts = [];
    const kfmt = (v) => (v >= 1000 ? `${Math.round(v / 1000)}k` : String(v));
    cc.series.forEach((s) => { const is = inp.series.find((x) => x.key === s.key); if (!is) return;
      s.points.forEach((p, i) => pts.push({ key: s.key, color: s.color, x: is.values[i], y: (100 * p.k) / p.n, tag: `${p.x}`,
        tip: tpl(b.tip || '{label} · {x} {unit}: {xv}, {k}/{n} ({pct}%)', { label: s.label, x: p.x, unit: UNIT, xv: fmt(Math.round(is.values[i])), k: p.k, n: p.n, pct: pct(p.k, p.n) }) })); });
    return card(b.title, b.sub || '', `
          ${pts.length ? slot((Wd) => scatter({ W: Wd, pts, xmin: b.xmin, xmax: b.xmax, xticks: b.xticks, xfmt: kfmt, xlabel: b.xlabel, ylabel: b.ylabel })) + legend(cc.series) : ''}`);
  };

  P.heatmap = (b) => {  // a rate per case category (rows) and variant × level (columns)
    const C = DS[b.data], fx = F.values || [];
    const cats = C.categories ? Object.keys(C.categories[`${VARS[0].key}@${fx[0]}`] || {}).sort() : [];
    const cols = order().flatMap((k) => fx.map((x) => [k, x]));
    if (!cats.length) return '';
    return card(b.title, b.sub || '', `<div class="hm" style="grid-template-columns:minmax(210px,2.2fr) repeat(${cols.length},minmax(34px,1fr))">
        <div></div>${order().map((k) => `<div class="hm-g" style="grid-column:span ${fx.length};--c:${col(k)}"><span class="sw" style="--c:${col(k)}"></span>${esc(vname(k))}</div>`).join('')}
        <div></div>${cols.map(([, x]) => `<div class="hm-x">${esc(x)}</div>`).join('')}
        ${cats.map((c) => { const n0 = ((C.categories[`${cols[0][0]}@${cols[0][1]}`] || {})[c] || [])[1];
          return `<div class="hm-r" title="${esc((D.groups || {})[c] || '')}"><b>${esc(c)}</b> ${esc((D.groups || {})[c] || '')}${n0 ? ` <span class="muted nw">n = ${n0}</span>` : ''}</div>${cols.map(([k, x]) => { const v = (C.categories[`${k}@${x}`] || {})[c];
          const r = v && v[1] ? v[0] / v[1] : null; return `<div class="hm-c" style="background:${heat(r)}" title="${esc(vname(k))} · ${x} ${esc(UNIT)} · ${esc(c)}: ${v ? `${v[0]}/${v[1]}` : esc(b.none || 'no cases')}">${v ? `${v[0]}/${v[1]}` : '—'}</div>`; }).join('')}`; }).join('')}
      </div>`);
  };

  P.mix = (b) => {  // the rows that did not pass, by their note (a failure class), per variant
    const cls = classes(runById(PRE)), names = cls.map((c) => c.label);
    const maxInc = Math.max(1, ...order().map((k) => cls.reduce((a, c) => a + (c.rows[k] || []).length, 0)));
    W.push((m) => $$('[data-mix]', m).forEach((el) => el.addEventListener('click', () => { const [i, k] = el.dataset.mix.split(':'); const c = cls[+i]; openDrawer({ type: 'list', title: c.label, sub: vname(k), rows: c.rows[k], run: PRE }); })));
    return card(b.title, b.sub || '', `<div class="mix">${order().map((k) => { const tot = cls.reduce((a, c) => a + (c.rows[k] || []).length, 0);
        return `<div class="mix-r"><span><span class="sw" style="--c:${col(k)}"></span>${esc(vname(k))}</span><div class="mix-b" style="width:${(100 * tot) / maxInc}%">${cls.map((c, i) => (c.rows[k] || []).length
          ? `<i style="flex:${c.rows[k].length};background:${PALETTE[i % PALETTE.length]}" data-mix="${i}:${esc(k)}" title="${esc(c.label)}: ${c.rows[k].length}"></i>` : '').join('')}</div><b>${tot}</b></div>`; }).join('')}</div>
      <div class="legend" style="justify-content:flex-start">${names.map((n, i) => `<span><span class="sw" style="--c:${PALETTE[i % PALETTE.length]}"></span>${esc(n)}</span>`).join('')}</div>`);
  };

  P.paired_tests = (b) => {  // exact tests on discordant pairs, drawn as two bars
    const td = DS[b.data], tmax = Math.max(1, ...td.map((t) => Math.max(t.a_only, t.b_only)));
    const only = (n) => tpl(b.only || 'only {name}', { name: n });
    return card(b.title, b.sub || '', `<div class="dvs">${td.map((t) => { const bk = (VARS.find((v) => v.name === t.b) || {}).key, ak = (VARS.find((v) => v.name === t.a) || {}).key;
      return `<div class="dv" data-metric="${esc(t.metric)}"><div class="dv-h"><b>${esc(t.a)} vs ${esc(t.b)}</b>${pill(t.sig ? `Significant · p ${String(t.p).startsWith('<') ? t.p : `= ${t.p}`}` : `Not significant · p = ${t.p}`, t.sig ? 'ok' : 'bad')}</div>
        <div class="dv-b"><span class="dv-n">${t.b_only}</span><div class="dv-l"><i style="width:${(100 * t.b_only) / tmax}%;background:${col(bk)}"></i></div><div class="dv-r"><i style="width:${(100 * t.a_only) / tmax}%;background:${col(ak)}"></i></div><span class="dv-n">${t.a_only}</span></div>
        <div class="dv-k"><span>${esc(only(t.b))}</span><span>${esc(only(t.a))}</span></div></div>`; }).join('')}</div>`);
  };

  P.comparison = (b) => {  // every measure per variant at one level, in groups; and a rate per case category
    const C = DS[b.data], groups = b.groups || [], g = groups.find((x) => x.id === S.tab.comparison) || groups[0], sz = S.size;
    const keys = VARS.map((v) => v.key);
    const seg = `<div class="seg">${(C.sizes || []).map((s) => `<button type="button" data-size="${s}" class="${s === sz ? 'on' : ''}">${s} ${esc(UNIT)}</button>`).join('')}</div>`;
    let table;
    if (S.tab.comparison === 'category') {
      const cats = Object.keys((C.categories || {})[`${keys[0]}@${sz}`] || {}).sort();
      table = `<table class="t"><thead><tr><th>Category</th>${keys.map((k) => `<th class="n"><span class="sw" style="--c:${col(k)}"></span>${esc(vname(k))}</th>`).join('')}</tr></thead><tbody>
        ${cats.map((c) => `<tr><td><b>${esc(c)}</b> <span class="muted">${esc((D.groups || {})[c] || '')}</span></td>${keys.map((k) => { const v = C.categories[`${k}@${sz}`][c];
          return `<td class="n c-${esc(VAR[k].color)}">${v[0]}/${v[1]}</td>`; }).join('')}</tr>`).join('')}</tbody></table>`;
    } else {
      table = `<table class="t"><thead><tr><th>Metric</th>${keys.map((k) => `<th class="n"><span class="sw" style="--c:${col(k)}"></span>${esc(vname(k))}</th>`).join('')}</tr></thead><tbody>
        ${g.rows.map((r) => { const vals = keys.map((k) => C.cells[`${k}@${sz}`][r.m]);
          const num = vals.map((v) => (Array.isArray(v) ? (v[1] ? v[0] / v[1] : null) : v));
          const best = r.better ? (r.better === 'high' ? Math.max(...num.filter((v) => v != null)) : Math.min(...num.filter((v) => v != null))) : null;
          return `<tr><td>${esc(r.label)}${r.note ? `<span class="sub">${esc(r.note)}</span>` : ''}</td>${vals.map((v, i) => {
            const k = keys[i], isBest = best != null && num[i] === best && new Set(num).size > 1;
            const red = g.alarm && r.better === 'low' && num[i] > 0;
            const cls = `n c-${red ? 'red' : VAR[k].color}${isBest ? ' best' : ''}`;
            if (Array.isArray(v)) return `<td class="${cls}">${v[1] ? `${pct(v[0], v[1])}%` : '—'}<span class="sub">${v[0]}/${v[1]}</span></td>`;
            return `<td class="${cls}">${fmt(v)}</td>`; }).join('')}</tr>`; }).join('')}</tbody></table>`;
    }
    W.push((m) => $$('[data-size]', m).forEach((x) => x.addEventListener('click', () => { S.size = +x.dataset.size; render(); })));
    return head(b.heading || 'Variant comparison', b.sub || '') +
      `<div class="tbar">${tabs('comparison', [...groups.map((x) => [x.id, x.label]), ['category', b.category_tab || 'By category']])}${seg}</div>
       <div class="twrap">${table}</div>${b.callout ? `<div class="callout" style="margin-top:16px">${ic(b.callout_icon || 'shield')}<div>${md(b.callout)}</div></div>` : ''}`;
  };

  P.funnel = (b) => {  // per variant: rows at each stage, the stage that stopped them, and what reached the end
    const C = DS[b.data], k = S.safety, sr = (C.series || []).find((s) => s.key === k) || { values: [] }, met = MET[`${b.metric || ''}${k}`] || {};
    const st = b.stages || [], gov = (VAR[k] || {}).governed, last = sr.values[sr.values.length - 1];
    const bk = met.breakdown || [], max = Math.max(1, ...bk.map((x) => x.count));
    const fx = F.values || [], by = b.by_level, cells = (DS[by && by.data] || {}).cells;
    const cellsOk = by && cells && fx.every((x) => (cells[`${k}@${x}`] || {})[by.first]);
    const bySize = cellsOk ? (() => { const vals = fx.map((x) => ({ x, p: cells[`${k}@${x}`][by.first], e: cells[`${k}@${x}`][by.last] }));
      const mx = Math.max(1, ...vals.map((v) => v.p[0]));
      return `<div class="bars">${vals.map((v) => `<div class="bars-r"><span>${esc(v.x)} ${esc(UNIT)}</span><div class="bars-b"><i class="p" style="width:${(100 * v.p[0]) / mx}%"></i><i class="e" style="width:${(100 * v.e[0]) / mx}%"></i></div>
        <span class="small">${v.p[0]} ${esc(by.first_word || '')} · <b class="${v.e[0] ? 'no-t' : 'ok-t'}">${v.e[0]} ${esc(by.last_word || '')}</b> of ${v.p[1]}</span></div>`).join('')}</div>
        <div class="legend" style="justify-content:flex-start"><span><span class="sw" style="--c:#FDE3C3"></span>${esc((st[0] || {}).label || '')}</span><span><span class="sw" style="--c:var(--red)"></span>${esc((st[st.length - 1] || {}).label || '')}</span></div>`; })() : '';
    const stage = (s, i) => `<div class="st s${i + 1}${i === st.length - 1 ? ` last ${last ? 'some' : 'zero'}` : ''}"><div><b>${esc(sr.values[i])}</b><span>${esc(gov && s.governed ? s.governed : s.label)}</span></div></div>`;
    W.push((m) => {
      $$('[data-var]', m).forEach((x) => x.addEventListener('click', () => { S.safety = x.dataset.var; render(); }));
      $$('[data-bk]', m).forEach((x) => x.addEventListener('click', () => { const r = bk[+x.dataset.bk]; openDrawer({ type: 'list', title: r.label, rows: r.rows, run: PRE, sub: vname(k) }); }));
    });
    const tb = b.table || {};
    return head(b.heading || '', b.sub || '', `<div class="seg">${VARS.map((v) => `<button type="button" data-var="${esc(v.key)}" class="${v.key === k ? 'on' : ''}">${esc(v.name)}</button>`).join('')}</div>`) +
      `<div class="grid g12">
        <section class="card"><h2>${esc(b.title || '')} · ${esc(vname(k))}</h2><p class="sub">${esc(tpl(b.of || '{n}', { n: sr.n }))}</p>
          <div class="funnel">${st.map(stage).join('\n            ')}</div></section>
        <section class="card"><h2>${esc(met.breakdown_title || 'Breakdown')}</h2><p class="sub">${met.sub ? `${esc(met.sub)}. ` : ''}Select a bar to see its rows.</p>
          ${hbars(bk, max, last && !gov ? 'var(--red)' : 'var(--orange)', (r, i) => `data-bk="${i}"`)}
          ${(met.explain || []).length ? `<table class="t" style="margin-top:14px"><tbody>${met.explain.map(([a, b2]) => `<tr><td>${esc(a)}</td><td class="n"><b>${esc(b2)}</b></td></tr>`).join('')}</tbody></table>` : ''}</section>
      </div>
      <div class="callout ${last ? 'bad' : 'ok'}" style="margin-top:16px">${ic(b.icon || 'shield')}<div>${md((b.notes || {})[k] || '')}</div></div>
      <div class="grid g2">
        ${bySize ? `<section class="card"><h2>${esc(by.title || '')} · ${esc(vname(k))}</h2><p class="sub">${esc(by.sub || '')}</p>${bySize}</section>` : ''}
        <section class="card"><h2>${esc(tb.title || '')}</h2><p class="sub">${esc(tpl(tb.sub || '', { factor: FL }))}</p>
          <div class="twrap"><table class="t"><thead><tr>${(tb.head || []).map((h, i) => `<th${i && i < 4 ? ' class="n"' : ''}>${esc(h)}</th>`).join('')}</tr></thead><tbody>
          ${(C.series || []).map((s) => { const e = s.values[s.values.length - 1];
            return `<tr class="link" data-metric="${esc((b.metric || '') + s.key)}"><td class="nw"><span class="sw" style="--c:${col(s.key)}"></span>${esc(s.label)}</td>
            <td class="n">${s.n}</td><td class="n">${s.values[0]}</td><td class="n ${e ? 'c-red' : 'c-green'}"><b>${e}</b></td><td class="muted">${esc((VAR[s.key] || {})[tb.field] || '')}</td></tr>`; }).join('')}</tbody></table></div></section>
      </div>`;
  };

  // ---------------------------------------------------------------- case explorer
  function filtered() {
    const R = runById(S.f.run), q = S.f.q.toLowerCase();
    return R.rows.filter((r) => (!S.f.key || r.key === S.f.key) && (!S.f.x || String(r.x) === S.f.x) && (!S.f.g || caseOf(r.case).group === S.f.g)
      && (!S.f.res || (S.f.res === 'pass' ? r.pass : S.f.res === 'fail' ? !r.pass : r.sev === S.f.res))
      && (S.list === 'all' || (S.list === 'fail' ? !r.pass : r.sev !== 'none'))
      && (!q || `${r.id} ${caseOf(r.case).title} ${r.note || ''}`.toLowerCase().includes(q)))
      .sort((a, b) => (caseOf(a.case).group + a.case).localeCompare(caseOf(b.case).group + b.case, 'en', { numeric: true }) || a.key.localeCompare(b.key) || a.x - b.x);
  }
  const colCell = (c, r, C) => (c.show === 'result' ? res(r) : c.show === 'severity' ? sevPill(r) : c.case_fact ? esc(fact(C, c.case_fact) || '—')
    : c.kv ? esc(((r.kv || []).find((x) => x[0] === c.kv) || [])[1] || '—') : '');
  P.case_explorer = (b) => {
    const R = runById(S.f.run), rows = filtered(), pages = Math.max(1, Math.ceil(rows.length / PER)), cols = b.columns || [];
    S.page = Math.min(S.page, pages);
    const all = R.rows, sel = (name, opts, v) => `<select data-f="${name}">${opts.map(([val, l]) => `<option value="${esc(val)}" ${String(v) === String(val) ? 'selected' : ''}>${esc(l)}</option>`).join('')}</select>`;
    const groups = [...new Set(all.map((r) => caseOf(r.case).group))].sort();
    const page = rows.slice((S.page - 1) * PER, S.page * PER);
    const pg = [];
    for (let i = 1; i <= pages; i++) if (i === 1 || i === pages || Math.abs(i - S.page) <= 1) pg.push(i); else if (pg[pg.length - 1] !== '…') pg.push('…');
    const flagged = SEV.filter((s) => s.id !== 'none');
    W.push((m) => {
      $$('[data-f]', m).forEach((s) => s.addEventListener('change', () => { S.f[s.dataset.f] = s.value; S.page = 1; render(); }));
      $$('[data-list]', m).forEach((x) => x.addEventListener('click', () => { S.list = x.dataset.list; S.page = 1; render(); }));
      $$('[data-p]', m).forEach((x) => x.addEventListener('click', () => { S.page = +x.dataset.p; render(); }));
      $$('[data-row]', m).forEach((t) => t.addEventListener('click', () => go(`#row=${S.f.run}/${t.dataset.row}`)));
      $('#clear', m).addEventListener('click', () => { S.f = { run: S.f.run, key: '', x: '', g: '', res: '', q: '' }; S.list = 'all'; S.page = 1; render(); });
      const q = $('#q', m); q.addEventListener('input', () => { S.f.q = q.value; S.page = 1; const p = q.selectionStart; render(); const n = $('#q'); n.focus(); n.setSelectionRange(p, p); });
      $('#csv', m).addEventListener('click', () => download(`${S.f.run}-rows.csv`, csvOf(rows), 'text/csv'));
    });
    return head(b.heading || 'Case explorer', `${esc(R.label)}: ${esc(R.note || '')}`, `<button class="btn" id="csv" type="button">${ic('download')}Export CSV</button>`) +
      `<div class="cases">
        <aside class="card filters"><h2 style="margin-bottom:12px">Filters</h2>
          <label>Run</label>${sel('run', RUNS.map((r) => [r.id, `${r.label} · ${r.rows.length}`]), S.f.run)}
          <label>Variant</label>${sel('key', [['', 'All variants'], ...VARS.map((v) => [v.key, v.name])], S.f.key)}
          <label>${esc(F.label || 'Level')}</label>${sel('x', [['', F.all || 'All'], ...(F.values || []).map((x) => [x, `${x} ${UNIT}`])], S.f.x)}
          <label>Category</label>${sel('g', [['', 'All categories'], ...groups.map((g) => [g, `${g} · ${(D.groups || {})[g] || ''}`])], S.f.g)}
          <label>Result</label>${sel('res', [['', 'All results'], ['pass', RES.pass], ['fail', RES.fail], ...flagged.map((s) => [s.id, s.label])], S.f.res)}
          <button class="btn" type="button" id="clear">Clear filters</button></aside>
        <section class="card" style="padding:16px 18px"><div class="tbar">
          ${`<div class="tabs">${[['all', `Rows (${all.length})`], ['fail', `${RES.fail} (${all.filter((r) => !r.pass).length})`], ...(flagged.length ? [['flagged', `${b.flag_tab || 'Flagged'} (${all.filter((r) => r.sev !== 'none').length})`]] : [])].map(([id, l]) => `<button type="button" data-list="${id}" class="${S.list === id ? 'on' : ''}">${esc(l)}</button>`).join('')}</div>`}
          <input type="search" id="q" placeholder="${esc(b.search || 'Search rows…')}" value="${esc(S.f.q)}"></div>
          <div class="twrap"><table class="t"><thead><tr><th>Row</th><th>Variant</th><th class="n">${esc(F.label || '')}</th><th>Category</th>${cols.map((c) => `<th>${esc(c.label)}</th>`).join('')}</tr></thead><tbody>
          ${page.map((r) => { const c = caseOf(r.case); return `<tr class="link" data-row="${esc(r.id)}"><td><span class="mono">${esc(r.id)}</span><span class="sub one" title="${esc(c.title)}">${esc(c.title)}</span></td>
            <td class="nw"><span class="sw" style="--c:${col(r.key)}"></span>${esc(vname(r.key))}</td><td class="n">${esc(r.x)}</td><td>${esc(c.group)}</td>
            ${cols.map((cl) => `<td>${colCell(cl, r, c)}</td>`).join('')}</tr>`; }).join('') || `<tr><td colspan="${4 + cols.length}" class="muted">No rows match these filters.</td></tr>`}
          </tbody></table></div>
          <div class="pager"><button type="button" data-p="${S.page - 1}" ${S.page <= 1 ? 'disabled' : ''}>‹</button>${pg.map((p) => (p === '…' ? '<span>…</span>' : `<button type="button" data-p="${p}" class="${p === S.page ? 'on' : ''}">${p}</button>`)).join('')}
            <button type="button" data-p="${S.page + 1}" ${S.page >= pages ? 'disabled' : ''}>›</button><span>${rows.length} rows</span></div></section></div>`;
  };

  function caseDetail() {
    const { run: rid, id } = S.row, r = IDX[rid][id], C = caseOf(r.case), R = runById(rid);
    const list = filtered(), at = list.findIndex((x) => x.id === id);
    const prev = at > 0 ? list[at - 1] : null, next = at >= 0 && at < list.length - 1 ? list[at + 1] : null;
    const T = TR ? (TR[rid] || {})[id] : undefined, tabsList = E.case_tabs || [];
    let body;
    if (!TR) body = '<section class="card"><p class="muted">Unpacking the recorded evidence…</p></section>';
    else if (!T) body = '<section class="card"><p class="muted">No detail file was recorded for this row.</p></section>';
    else body = blocks((T.tabs || {})[S.tab.case] || [], { r, C, T });
    const s = sevOf(r), headPill = s.id === top.id && top.id !== 'none' ? pill(s.label, s.tone || 'bad') : r.pass ? pill(RES.pass, 'ok') : pill(RES.fail, 'bad');
    return `<a href="#${esc(CE_PAGE.id)}" class="btn" style="margin-bottom:14px">${ic('arrowL')}All cases</a>
      <div class="cd-h"><div><h1><span class="mono" style="font-size:22px">${esc(r.id)}</span>${headPill}</h1>
        <div class="meta">${esc(C.group)} · ${esc((D.groups || {})[C.group] || '')} · <span style="color:${col(r.key)}">${esc(vname(r.key))}</span> · ${esc(r.x)} ${esc(UNIT)} · ${esc(R.label)}</div></div>
        <div class="nav">${prev ? `<button class="btn" type="button" data-go="#row=${esc(rid)}/${esc(prev.id)}">${ic('arrowL')}Previous</button>` : ''}${next ? `<button class="btn" type="button" data-go="#row=${esc(rid)}/${esc(next.id)}">Next case${ic('arrowR')}</button>` : ''}</div></div>
      ${tabs('case', tabsList.map((t) => [t.id, t.label]))}${body}`;
  }

  // case-tab blocks (evidence_kit.blocks builds them)
  const mt = (v) => (v != null ? ` style="margin-top:${+v}px"` : '');
  const parts = (ps) => (ps || []).map(([k, a, b]) => ({ text: () => esc(a), md: () => md(a), code: () => `<code>${esc(a)}</code>`, sub: () => `<span class="sub">${esc(a)}</span>`,
    alert: () => `<span class="sub" style="color:var(--red)">${esc(a)}</span>`, pill: () => pill(a, b), dash: () => '—' }[k] || (() => ''))()).join('');
  const BL = {
    grid: (b, x) => `<div class="grid ${esc(b.cls || 'g2')}">${blocks(b.items, x)}</div>`,
    card: (b, x) => `<section class="card">${b.title ? `<h2>${esc(b.title)}</h2>` : ''}${b.sub != null ? `<p class="sub">${md(b.sub)}</p>` : ''}${blocks(b.items, x)}</section>`,
    kv: (b, x) => `<div class="kv"><h3>${esc(b.title)}</h3>${blocks(b.items, x)}</div>`,
    h3: (b) => `<h3${mt(b.mt)}>${esc(b.text)}</h3>`,
    quote: (b) => `<div class="quote"${mt(b.mt)}>“${esc(b.text)}”</div>`,
    line: (b) => `<div class="small"><span class="muted">${esc(b.label)}:</span> ${b.bold ? `<b>${esc(b.value)}</b>` : md(b.value)}</div>`,
    small: (b) => `<div class="small">${esc(b.text)}</div>`,
    muted: (b) => `<span class="muted">${esc(b.text)}</span>`,
    chips: (b) => { const h = b.items.map(([t, tone, title]) => `<span class="chipc ${esc(tone || '')}"${title ? ` title="${esc(title)}"` : ''}>${esc(t)}</span>`).join(''); return b.wrap ? `<div style="margin-top:6px">${h}</div>` : h; },
    chip: (b) => `<div class="chipc">${esc(b.text)}</div>`,
    steps: (b) => { const h = b.items.map((p) => `<div class="step"${p.mb != null ? ` style="margin-bottom:${+p.mb}px"` : ''}><div class="h">${p.span === false ? md(p.head) : `<span>${md(p.head)}</span>`}${p.pill ? pill(p.pill[0], p.pill[1]) : ''}</div>
          ${(p.lines || []).map((u) => `<div class="${esc(p.line_cls || 'u')}">${esc(u)}</div>`).join('')}</div>`).join(''); return b.bare ? h : `<div class="steps">${h}</div>`; },
    status: (b) => `<span class="${b.ok ? 'ok-t' : 'no-t'}">${b.ok ? '✓' : '✕'} ${esc(b.text)}</span>${esc(b.after || '')}${b.link ? `<a href="#" data-tab="case:${esc(b.link[1])}">${esc(b.link[0])}</a>` : ''}`,
    transcript: (b) => `<section class="card"><h2>${esc(b.title)}</h2><p class="sub">${esc(b.sub)}</p>${(b.events || []).map((e) => `<div class="ev"><span class="dot ${e.tone === 'ok' ? 'ok' : e.tone === 'bad' ? 'bad' : e.tone === 'warn' ? 'warn' : ''}">${esc(e.n ?? '')}</span>
      <div>${md(e.text)}${e.msg ? `<div class="msg">${esc(e.msg)}</div>` : ''}${e.code ? `<pre>${esc(e.code)}</pre>` : ''}${(e.notes || []).length ? `<div class="notes">${e.notes.map(md).join('<br>')}</div>` : ''}</div></div>`).join('')}</section>`,
    table: (b) => (b.rows.length || b.empty ? `<div class="twrap"><table class="t"><thead><tr>${b.head.map(([h, n]) => `<th${n ? ` class="${esc(n)}"` : ''}>${esc(h)}</th>`).join('')}</tr></thead><tbody>
      ${b.rows.map((r) => `<tr>${r.map((c, i) => { const k = c.cls || ((b.head[i] || [])[1] === 'n' ? 'n' : ''); return `<td${k ? ` class="${esc(k)}"` : ''}>${parts(c.parts)}</td>`; }).join('')}</tr>`).join('') || `<tr><td colspan="${b.head.length}" class="muted">${esc(b.empty)}</td></tr>`}
      </tbody></table></div>` : ''),
    files: (b) => `<div class="tree"><ul>${b.items.map((f) => `<li><span class="f">${ic('file')}${esc(f)}</span></li>`).join('')}</ul></div>`,
    callout: (b) => `<div class="callout ${esc(b.tone || '')}"${mt(b.mt)}>${ic(b.icon || 'alert')}<div>${esc(b.text)}</div></div>`,
    case_request: (b, x) => `<div class="quote">“${esc(x.C.title)}”</div><div class="small muted" style="margin-top:6px">${esc(x.C.who || '')}</div>`,
    case_facts: (b, x) => `${(x.C.facts || []).map(([k, v]) => `<div class="small" style="margin:3px 0"><span class="muted">${esc(k)}:</span> ${md(v)}</div>`).join('')}
          ${(x.C.chips || []).length ? `<div style="margin-top:6px">${x.C.chips.map((t) => `<span class="chipc ${esc(b.chip_tone || '')}" title="${esc(b.chip_title || '')}">${esc(t)}</span>`).join('')}</div>` : ''}`,
    row_flags: (b, x) => `<ul class="flags">${(x.r.flags || []).map(([k, v]) => `<li>${v == null ? '<span class="muted">—</span>' : v ? `<span class="y">${ic('check')}</span>` : `<span class="x">${ic('x')}</span>`}${esc(k)}</li>`).join('')}</ul>
          ${x.r.note ? `<div class="small" style="margin-top:6px"><span class="muted">${esc(b.note_label || 'Note')}:</span> ${esc(x.r.note)}</div>` : ''}`,
    row_measurements: (b, x) => `<table class="t"><tbody>${[...(x.r.metrics || []), ...(x.r.kv || [])].map(([k, v]) => `<tr><td>${esc(k)}</td><td class="n">${md(v)}</td></tr>`).join('')}</tbody></table>`,
  };
  const blocks = (bs, x) => (bs || []).map((b) => (BL[b.t] || (() => ''))(b, x)).join('');

  // ---------------------------------------------------------------- hypotheses
  P.hypotheses = (b) => {
    const hs = E.hypotheses || [], ok = hs.filter((h) => h.status === 'SUPPORTED').length;
    const st = (s) => (s === 'SUPPORTED' ? `<span class="st-ic ok">${ic('check')}Supported</span>` : /NOT|CONTRA/.test(s) ? `<span class="st-ic bad">${ic('x')}${esc(s.charAt(0) + s.slice(1).toLowerCase())}</span>` : `<span class="st-ic warn">${ic('alert')}${esc(s.charAt(0) + s.slice(1).toLowerCase())}</span>`);
    const pairs = (p) => (p || []).map(([a, c]) => `<div class="small"><span class="muted">${md(a)}:</span> <b>${md(c)}</b></div>`).join('');
    return head(b.heading || 'Hypotheses', b.sub || 'Written before the run and frozen with it.') +
      `<div class="twrap"><table class="t"><thead><tr><th>ID</th><th>Hypothesis</th><th>Expected</th><th>Observed</th><th>Status</th></tr></thead><tbody>
      ${hs.map((h) => `<tr><td><b>${esc(h.id)}</b></td><td>${md(h.title)}${h.note ? `<span class="sub">${md(h.note)}</span>` : ''}</td><td>${pairs(h.expected)}</td><td>${pairs(h.observed)}</td><td>${st(h.status)}</td></tr>`).join('')}
      </tbody></table></div><div class="callout" style="margin-top:16px">${ic('target')}<div><b>${ok} / ${hs.length} hypotheses supported.</b>${esc(b.closing || '')}</div></div>`;
  };

  // ---------------------------------------------------------------- failures
  function classes(R) {
    const m = {};
    R.rows.filter((r) => !r.pass).forEach((r) => { const k = r.note || 'other'; m[k] = m[k] || { label: k, rows: Object.fromEntries(VARS.map((v) => [v.key, []])) }; (m[k].rows[r.key] = m[k].rows[r.key] || []).push(r.id); });
    return Object.values(m).sort((a, b) => Object.values(b.rows).flat().length - Object.values(a.rows).flat().length);
  }
  P.failures = (b) => {
    const R = runById(PRE), cls = classes(R), fs = E.failures || [], t = S.tab.failures;
    const incorrect = R.rows.filter((r) => !r.pass).length, v = { gaps: fs.length, rows: incorrect, run: R.label.toLowerCase(), n: incorrect };
    let body = '';
    if (t === 'all') {
      body = `<section class="card"><h2>${esc(b.gaps_title || '')}</h2><p class="sub">${esc(b.gaps_sub || '')}</p><div class="fl">
        ${fs.map((f, i) => `<div class="fi ${S.open[i] ? 'open' : ''}" data-fail="${i}"><span class="id">${esc(b.prefix || '#')}${String(f.n).padStart(2, '0')}</span><div><b>${md(f.title)}</b><span class="s">${md(f.summary || '')}</span></div>${f.tag ? pill(f.tag, 'info') : ''}</div>
          ${S.open[i] ? `<div class="fd"><dl>${f.rows.map(([k, x]) => `<dt>${esc(k)}</dt><dd>${md(x)}</dd>`).join('')}</dl><div class="note">${md(f.note || '')}
            ${(f.row_ids || []).length ? ` · ${f.row_ids.map((x) => `<a href="#row=${esc(PRE)}/${esc(x)}">${esc(x)}</a>`).join(', ')}` : ''}</div></div>` : ''}`).join('')}</div></section>
        <section class="card"><h2>${esc(b.classes_title || '')}</h2><p class="sub">${esc(tpl(b.classes_sub || '', v))}</p>
          <div class="twrap"><table class="t"><thead><tr><th>${esc(b.class_col || 'Class')}</th>${VARS.map((x) => `<th class="n"><span class="sw" style="--c:${col(x.key)}"></span>${esc(x.name)}</th>`).join('')}</tr></thead><tbody>
          ${cls.map((c) => `<tr><td>${esc(c.label)}</td>${VARS.map((x) => `<td class="n">${(c.rows[x.key] || []).length ? `<a href="#" data-cls="${esc(c.label)}" data-k="${esc(x.key)}">${c.rows[x.key].length}</a>` : '<span class="muted">—</span>'}</td>`).join('')}</tr>`).join('')}
          </tbody></table></div></section>`;
    } else if (t === 'type') {
      const rows = cls.map((c) => ({ label: c.label, count: Object.values(c.rows).flat().length, rows: Object.values(c.rows).flat() }));
      body = card(b.type_title || '', b.type_sub || '', hbars(rows, Math.max(1, ...rows.map((x) => x.count)), 'var(--red)', (x, i) => `data-cl="${i}"`));
      S._cl = rows;
    } else {
      body = `<div class="grid g3">${VARS.map((x) => { const rows = cls.map((c) => ({ label: c.label, count: (c.rows[x.key] || []).length, rows: c.rows[x.key] || [], k: x.key })).filter((y) => y.count);
        return `<section class="card"><h2><span class="sw" style="--c:${col(x.key)}"></span>${esc(x.name)}</h2><p class="sub">${esc(tpl(b.variant_sub || '{inc} of {n}', { inc: R.rows.filter((r) => r.key === x.key && !r.pass).length, n: R.rows.filter((r) => r.key === x.key).length }))}</p>
          ${hbars(rows, Math.max(1, ...rows.map((y) => y.count)), col(x.key), (y) => `data-cls="${esc(y.label)}" data-k="${esc(x.key)}"`)}</section>`; }).join('')}</div>`;
    }
    W.push((m) => {
      $$('[data-fail]', m).forEach((x) => x.addEventListener('click', () => { S.open[x.dataset.fail] = !S.open[x.dataset.fail]; render(); }));
      $$('[data-cls]', m).forEach((a) => a.addEventListener('click', (e) => { e.preventDefault(); const c = cls.find((x) => x.label === a.dataset.cls); openDrawer({ type: 'list', title: a.dataset.cls, sub: vname(a.dataset.k), rows: c.rows[a.dataset.k], run: PRE }); }));
      $$('[data-cl]', m).forEach((a) => a.addEventListener('click', () => { const c = S._cl[+a.dataset.cl]; openDrawer({ type: 'list', title: c.label, sub: b.all_variants || 'all variants', rows: c.rows, run: PRE }); }));
    });
    const tl = b.tabs || ['All ({gaps} gaps · {rows} rows)', 'By type', 'By variant'];
    return head(b.heading || 'Failure analysis', b.sub || '') + tabs('failures', [['all', tpl(tl[0], v)], ['type', tl[1]], ['variant', tl[2]]]) + body;
  };

  // ---------------------------------------------------------------- artifacts (raw evidence)
  function tree(paths) {
    const root = {};
    paths.forEach(([p, why]) => { const ps = p.split('/'); let n = root; ps.forEach((x, i) => { n[x] = n[x] || (i === ps.length - 1 ? { __why: why } : {}); n = n[x]; }); });
    const walk = (n) => `<ul>${Object.keys(n).filter((k) => k !== '__why').map((k) => { const c = n[k], leaf = Object.keys(c).every((x) => x === '__why');
      return leaf ? `<li><span class="f">${ic('file')}${esc(k)}</span>${c.__why ? `<span class="why">${esc(c.__why)}</span>` : ''}</li>` : `<li><span class="d">${ic('folder')}${esc(k)}/</span>${walk(c)}</li>`; }).join('')}</ul>`;
    return `<div class="tree">${walk(root)}</div>`;
  }
  function revCard() {
    if (!REV) return '';
    return `<section class="card rev"><h2>Evidence revision ${esc(REV.id)}${REV.label ? ` · ${esc(REV.label)}` : ''}</h2>${REV.summary ? `<p class="sub">${md(REV.summary)}</p>` : ''}
      <table class="t"><tbody>${(REV.rows || []).map(([k, v]) => `<tr><td class="muted nw">${esc(k)}</td><td>${md(v)}</td></tr>`).join('')}</tbody></table></section>`;
  }
  const frozenTable = (fr) => `<div class="twrap"><table class="t"><thead><tr><th>Input</th><th>sha256</th><th>Today</th></tr></thead><tbody>${fr.map(([k, h, ok]) => `<tr><td class="mono">${esc(k)}</td><td class="mono muted nw">${esc(String(h).slice(0, 10))}…</td><td class="nw">${ok ? '<span class="ok-t">✓ match</span>' : '<span class="no-t">✕ drift</span>'}</td></tr>`).join('')}</tbody></table></div>`;
  P.artifacts = (b) => {
    const fr = A.frozen || [];
    W.push((m) => {
      $('#dl-json', m).addEventListener('click', () => download('evidence.json', JSON.stringify(E, null, 1), 'application/json'));
      $('#dl-csv', m).addEventListener('click', () => download(`${PRE}-rows.csv`, csvOf(runById(PRE).rows), 'text/csv'));
    });
    return head(b.heading || 'Raw evidence', b.sub || 'Where every number on these pages comes from. Nothing here is summarised.') +
      `<div class="grid g2"><section class="card"><h2>Run artifacts</h2><p class="sub">The recorded files behind this page, in the repository.</p>${tree(b.files || [])}
          <div class="dl"><button class="btn primary" type="button" id="dl-json">${ic('download')}Download evidence.json</button><button class="btn" type="button" id="dl-csv">${ic('download')}Rows CSV · ${esc(runById(PRE).label)}</button></div></section>
        <section class="card"><h2>Frozen inputs</h2><p class="sub">${fr.filter((f) => f[2]).length}/${fr.length} hashes match today</p>
          ${frozenTable(fr)}</section></div>
      ${revCard()}
      <div class="grid g2"><section class="card"><h2>Run metadata</h2><table class="t"><tbody>${(A.run_meta || b.run_meta || []).map(([k, v]) => `<tr><td class="muted">${esc(k)}</td><td>${esc(v)}</td></tr>`).join('')}
          ${(A.models || []).map(([k, v]) => `<tr><td class="muted">${esc(b.digest_label || 'frozen digest')}</td><td class="mono">${esc(k)} ${esc(v)} ${A.models_checked ? '<span class="ok-t">✓</span>' : ''}</td></tr>`).join('')}</tbody></table></section>
        <section class="card"><h2>Cross-checks</h2><p class="sub">The page is not built unless these hold.</p>${(A.checks || []).map((c) => `<div class="small" style="margin:6px 0"><span class="ok-t">✓</span> ${esc(c)}</div>`).join('')}
          <div class="lbl" style="margin-top:16px">Recorded runs</div>${RUNS.map((r) => `<div class="small" style="margin:6px 0"><b>${esc(r.label)}</b> · ${r.rows.length} rows · <span class="mono muted">${esc(r.path || '')}</span></div>`).join('')}</section></div>`;
  };

  // ---------------------------------------------------------------- reproduce
  P.reproduce = (b) => {
    const rp = RP || {}, t = S.tab.repro;
    let body;
    if (t === 'quick') body = `<section class="card"><h2>Quick start</h2><p class="sub">${esc(b.quick_sub || '')}</p>
        <pre class="code">${(b.quickstart || []).map(([c, cmd]) => `<span class="cm"># ${esc(c)}</span>\n${cmd.split('\n').map((l) => `<span class="ps">$</span> ${esc(l)}`).join('\n')}`).join('\n\n')}</pre>
        <div class="callout ok">${ic('check')}<div><b>${esc(b.replay_title || 'Replay')}</b>${esc(rp.reproduced)}/${esc(rp.rows)} recorded rows reproduced, with ${esc(rp.mismatches)} request mismatches.${b.replay_note ? ` ${md(b.replay_note)}` : ''}</div></div></section>`;
    else if (t === 'env') body = `<section class="card"><h2>Environment</h2><div class="twrap"><table class="t"><thead><tr><th>Component</th><th>Recorded run</th><th>To reproduce</th></tr></thead><tbody>
        ${(b.environment || []).map(([a, c, d]) => `<tr><td><b>${esc(a)}</b></td><td>${esc(c)}</td><td class="muted">${esc(d)}</td></tr>`).join('')}</tbody></table></div></section>`;
    else if (t === 'data') body = revCard() + `<section class="card"><h2>Frozen data</h2><p class="sub">${esc(b.frozen_sub || '')}</p>${frozenTable(A.frozen || [])}</section>`;
    else body = `<div class="grid g2"><section class="card"><h2>Replayed rows</h2><p class="sub">${esc(b.replay_sub || '')}${b.replay_note ? ` ${md(b.replay_note)}` : ''}</p>
        <div class="twrap"><table class="t"><thead><tr><th>Row</th><th>Reproduced</th><th class="n">Mismatches</th></tr></thead><tbody>${(rp.detail || []).map(([id, ok, mm, run]) => `<tr class="link" data-go="#row=${esc(run || (RUNS.find((r) => r.kind === 'replay') || RUNS[0]).id)}/${esc(id)}"><td class="mono">${esc(id)}</td><td>${ok ? `<span class="ok-t">✓ ${esc(b.reproduced_as || 'reproduced')}</span>` : '<span class="no-t">✕</span>'}</td><td class="n">${esc(mm)}</td></tr>`).join('')}</tbody></table></div></section>
      <section class="card"><h2>Noise floor</h2><p class="sub">${esc(b.noise_sub || '')}</p><div class="twrap"><table class="t"><thead><tr>${(b.noise_head || []).map((h, i) => `<th${i ? ' class="n"' : ''}>${esc(h)}</th>`).join('')}</tr></thead><tbody>
        ${(A.noise || []).map((r) => `<tr>${r.map((c, i) => `<td class="${i ? 'n' : ''}">${esc(c)}</td>`).join('')}</tr>`).join('')}</tbody></table></div></section></div>`;
    return head(b.heading || 'Reproducibility', b.sub || 'Run this experiment yourself.') + tabs('repro', [['quick', 'Quick start'], ['env', 'Environment'], ['data', 'Data'], ['replay', 'Replay']]) + body;
  };

  // ---------------------------------------------------------------- generic primitives for other learnings
  P.metric_grid = (b) => `<div class="kpis"${b.style ? ` style="${esc(b.style)}"` : ''}>${(b.items || []).map((x) => `<div class="kpi"${x.metric ? ` data-metric="${esc(x.metric)}"` : ''}><b>${esc(x.value)}</b><span>${esc(x.label)}</span></div>`).join('')}</div>`;
  P.table = (b) => { const d = DS[b.data] || {}, rows = d.rows || b.rows || [], hd = d.head || b.head || [];
    return card(b.title, b.sub, `<div class="twrap"><table class="t"><thead><tr>${hd.map((h, i) => `<th${i && b.numeric ? ' class="n"' : ''}>${esc(h)}</th>`).join('')}</tr></thead><tbody>
      ${rows.map((r) => `<tr${r.row ? ` class="link" data-go="#row=${esc(r.run || PRE)}/${esc(r.row)}"` : ''}>${(r.cells || r).map((c, i) => `<td${i && b.numeric ? ' class="n"' : ''}>${md(c)}</td>`).join('')}</tr>`).join('')}</tbody></table></div>`); };
  P.timeline = (b) => { const d = DS[b.data] || {};  // ordered events: {at, title, sub, tone, row}
    return card(b.title, b.sub, (d.events || []).map((e) => `<div class="ev tl"${e.row ? ` data-go="#row=${esc(e.run || PRE)}/${esc(e.row)}"` : ''}><span class="at ${esc(e.tone || '')}">${esc(e.at ?? '')}</span>
      <div>${md(e.title)}${e.sub ? `<div class="msg">${esc(e.sub)}</div>` : ''}</div></div>`).join('')); };
  P.distribution = (b) => { const d = DS[b.data] || {};  // {unit, series: [{key, label, color, values}]}
    return card(b.title, b.sub, slot((Wd) => boxes({ W: Wd, series: d.series || [], unit: d.unit })) + legend(d.series || [])); };

  // ---------------------------------------------------------------- proof (pae-proof/v1): the published run's experiments, checks and claims
  // 5.1: `verification = true` puts evidence verification and the experimental findings side by side, as separate verdicts
  const verdicts = () => { const v = (PR.integrity || {}).verification || {}, c = PR.counts || {}, fc = PR.finding_counts || {}, nf = Object.values(fc).reduce((a, n) => a + n, 0);
    return `<div class="kpis pk vd" style="grid-template-columns:repeat(2,minmax(0,1fr));margin:18px 0 14px"><div class="kpi t-${v.verified ? 'green' : 'red'}"><b>${!v.sections ? 'Not run' : v.verified ? 'VERIFIED' : 'NOT VERIFIED'}</b><span>Evidence verification${v.command ? ` · <code>${esc(v.command)}</code>` : ''}</span></div>
      <div class="kpi t-blue"><b>${fmt(c.pass || 0)} pass · ${fmt(nf)} findings · ${fmt(c.expected_failure || 0)} expected failure</b><span>Experimental findings: ${Object.entries(fc).map(([f, n]) => `${fmt(n)} ${esc(fdLabel(f).toLowerCase())}`).join(', ') || 'none'}</span></div></div>`; };
  P.proof_hero = (b) => `<section class="card proof-hero">${b.kicker ? `<div class="lbl">${esc(b.kicker)}</div>` : ''}<h1 class="pht">${(b.lines || []).map((l) => `<span>${md(l)}</span>`).join('')}</h1>
      ${b.verification ? verdicts() : ''}
      ${b.sub ? `<p class="question">${md(b.sub)}</p>` : ''}<div class="kpis pk">${(b.cards || []).map(([v, l, tone]) => `<div class="kpi${tone ? ` t-${esc(tone)}` : ''}"><b>${esc(v)}</b><span>${esc(l)}</span></div>`).join('')}</div>
      ${b.meta ? `<p class="small muted" style="margin:12px 0 0">${md(b.meta)}</p>` : ''}</section>`;
  P.profile = (b) => { const pf = PR.profile || {};
    const cls = (pf.classes || []).map((c) => `<section class="rc t-${esc(RC[c.class] || 'grey')}"><h3><span class="rk">${esc(c.class)}</span></h3>${c.meaning ? `<p class="small muted">${md(c.meaning)}</p>` : ''}
        <ul>${(c.items || []).map((it) => `<li>${md(it.text)}${it.check ? ` ${chk(it.check)}` : ''}</li>`).join('')}</ul></section>`).join('');
    const rows = (pf.groups || []).map((g) => `<tr class="grp"><td colspan="3">${esc(g.group)}</td></tr>${(g.rows || []).map(([k, v, c]) => `<tr><td class="muted">${esc(k)}</td><td>${md(v)}</td><td class="n">${c ? chk(c) : ''}</td></tr>`).join('')}`).join('');
    return (b.heading ? head(b.heading, b.sub) : '') + (cls ? card(b.classes_title || null, b.classes_sub || null, `<div class="reality">${cls}</div>`) : '') +
      (rows ? card(b.table_title || null, b.table_sub || null, `<div class="twrap"><table class="t prof"><tbody>${rows}</tbody></table></div>`) : ''); };
  P.scorecard = (b) => { const c = PR.counts || {};
    return card(b.title || null, tpl(b.sub || '', c), `<div class="twrap"><table class="t sc"><thead><tr>${(b.head || ['', '', '', '']).map((h) => `<th>${esc(h)}</th>`).join('')}</tr></thead><tbody>
      ${(PR.experiments || []).map((x) => `<tr class="link" data-exp="${esc(x.id)}"><td><b>${esc(x.id)}</b><div class="small">${esc(x.title)}</div></td><td class="small">${md(x.question || '')}</td><td>${fdPill(x)}</td><td>${x.checks.map(chk).join('')}</td></tr>`).join('')}</tbody></table></div>
      ${Object.keys(PR.finding_counts || {}).length ? `<p class="small" style="margin:10px 0 0"><b>${esc(b.findings_label || 'Findings reported, not errors')}:</b> ${Object.entries(PR.finding_counts).map(([f, n]) => `${pill(fdLabel(f), fdCls(f))} ${fmt(n)}`).join(' ')}</p>` : ''}
      ${b.note ? `<p class="small muted" style="margin:10px 0 0">${md(b.note)}</p>` : ''}`); };
  P.claim_trace = (b) => card(b.title || null, b.sub || null, `<div class="twrap"><table class="t ct"><thead><tr>${(b.head || ['', '', '', '', '']).map((h) => `<th>${esc(h)}</th>`).join('')}</tr></thead><tbody>
      ${(PR.claims || []).map((c) => `<tr class="link" data-clm="${esc(c.id)}"><td><b>${esc(c.id)}</b><div class="small">${md(c.statement)}</div></td><td>${stPill(c.verdict)}</td>
        <td class="small">${(c.experiments || []).map((x) => `<a href="#" data-exp="${esc(x)}">${esc(x)}</a>`).join('<br>')}</td><td>${(c.checks || []).map(chk).join('') || `<span class="small muted">${md(c.rests_on || '')}</span>`}</td>
        <td class="small muted">${where(c.article)}</td></tr>`).join('')}</tbody></table></div>`);
  const where = (locs) => { const L = locs || [], figs = L.filter((a) => a.startsWith('fig:')).map((a) => a.slice(4)), secs = L.filter((a) => !a.startsWith('fig:'));
    return secs.map(esc).join('<br>') + (figs.length ? `<div class="figs">${figs.map(esc).join(' · ')}</div>` : ''); };
  P.integrity = (b) => { const G = PR.integrity || {}, v = G.verification || {}, h = G.sha256sums || {}, cmp = G.comparison || {};
    const secs = (v.sections || []).map((x) => `<tr><td>${esc(x.section)}</td><td>${stPill(x.status)}</td><td class="small">${md(x.detail || '')}</td></tr>`).join('');
    return `<div class="grid g2">${card(b.verify_title || null, tpl(b.verify_sub || '', { verdict: !v.sections ? 'not run yet' : v.verified ? 'VERIFIED' : 'NOT VERIFIED', command: v.command || '' }), secs ? `<div class="twrap"><table class="t"><tbody>${secs}</tbody></table></div>` : '')}
      ${h.files ? card(b.hash_title || null, tpl(b.hash_sub || '', h), `${(h.groups || []).map(([g, n]) => `<div class="small" style="margin:4px 0"><b>${fmt(n)}</b> ${esc(g)}</div>`).join('')}${b.hash_note ? `<p class="small muted" style="margin:10px 0 0">${md(b.hash_note)}</p>` : ''}`) : ''}</div>
      ${cmp.classes ? card(b.cmp_title || null, tpl(b.cmp_sub || '', cmp), `<div class="twrap"><table class="t"><tbody>${Object.entries(cmp.classes).map(([k, n]) => `<tr><td>${esc(stLabel(k))}</td><td class="n"><b>${fmt(n)}</b></td></tr>`).join('')}</tbody></table></div>${cmp.note ? `<p class="small muted" style="margin:10px 0 0">${md(cmp.note)}</p>` : ''}`) : ''}`; };
  P.control = (b) => { const c = PR.control || {}, g = c.governed || {}, m = c.mutated || {};
    return card(b.title || null, c.safeguard_removed ? `Safeguard removed: ${c.safeguard_removed}` : null, `<div class="grid g2 ctl">
        <div class="ctl-c ok"><span class="lbl">${esc(b.governed_label || '')}</span><b>${fmt(g.reached_backend)}</b><span class="small">${esc(tpl(b.of || '', c))}</span></div>
        <div class="ctl-c bad"><span class="lbl">${esc(b.mutated_label || '')}</span><b>${fmt(m.reached_backend)}</b><span class="small">${esc(tpl(b.of || '', c))}</span></div></div>
      <dl class="kvl" style="margin-top:14px">${(b.fields || []).map(([k, f]) => (c[f] != null ? `<dt>${esc(k)}</dt><dd>${f === 'result' ? fdPill(c) : md(c[f])}</dd>` : '')).join('')}</dl>
      ${(c.fixtures || []).length ? `<div class="lbl" style="margin:14px 0 6px">${esc(tpl(b.fixtures_title || '', c))}</div><div class="twrap"><table class="t"><thead><tr>${(b.fixtures_head || []).map((x) => `<th>${esc(x)}</th>`).join('')}</tr></thead><tbody>
        ${c.fixtures.map((f) => `<tr${IDX[f.run] && IDX[f.run][f.row] ? ` class="link" data-go="#row=${esc(f.run)}/${esc(f.row)}"` : ''}><td class="mono small">${esc(f.row)}</td><td class="mono small">${esc(f.implementation)}</td><td class="small">${esc(f.governed)}</td><td class="small">${esc(f.mutated)}</td></tr>`).join('')}</tbody></table></div>` : ''}`); };

  // ---------------------------------------------------------------- the evidence drawer: a number, then its rows and where it comes from
  function openDrawer(level) { S.drawer = [level]; drawer(); }
  function provenance(m) {
    const f = (E.facts || {})[m.source];
    if (!f) return '';
    const rows = [['Derivation', f.derivation], ['Rows', f.rows ? `${f.rows.ids.length} in ${f.rows.run}` : null], ['Source', f.source], ['Frozen', f.freeze || (E.provenance || {}).freeze]].filter(([, v]) => v);
    return rows.length ? `<div class="lbl" style="margin:16px 0 6px">How this number was derived</div><dl class="kvl">${rows.map(([k, v]) => `<dt>${esc(k)}</dt><dd>${md(v)}</dd>`).join('')}</dl>` : '';
  }
  function drawer() {
    const d = $('#drawer'), top2 = S.drawer[S.drawer.length - 1];
    if (!top2) { d.className = 'drawer'; d.innerHTML = ''; return; }
    let h = '';
    if (top2.type === 'metric') {
      const m = MET[top2.id];
      if (!m) { S.drawer = []; return drawer(); }
      h = `<span class="lbl">${esc(vname(m.variant))}</span><h2>${esc(m.headline)}</h2><p class="lead">${esc(m.statement)}</p><p class="small muted">${esc(m.sub || '')}</p>
        ${(m.explain || []).length ? `<dl class="kvl">${m.explain.map(([k, v]) => `<dt>${esc(k)}</dt><dd>${esc(v)}</dd>`).join('')}</dl>` : ''}
        ${(m.breakdown || []).length ? `<div class="lbl" style="margin-bottom:6px">${esc(m.breakdown_title || 'Breakdown')}</div>${hbars(m.breakdown, Math.max(1, ...m.breakdown.map((x) => x.count)), col(m.variant), (x, i) => `data-dbk="${i}"`)}` : ''}
        ${(m.rows || []).length ? `<button class="btn" type="button" id="dall" style="margin-top:14px">All ${m.rows.length} rows${ic('arrowR')}</button>` : ''}${provenance(m)}`;
    } else if (top2.type === 'check' || top2.type === 'experiment' || top2.type === 'claim') {
      h = proofDrawer(top2);
      if (!h) { S.drawer = []; return drawer(); }
    } else {
      h = `<span class="lbl">${esc(top2.sub || '')}</span><h2>${esc(top2.title)}</h2><p class="lead">${top2.rows.length} rows · select one to open its evidence</p>
        <div class="rows">${top2.rows.map((id) => { const r = IDX[top2.run][id]; const c = r ? caseOf(r.case) : {}; return `<a href="#row=${esc(top2.run)}/${esc(id)}"><div><span>${esc(id)}</span><div class="small muted">${esc(c.title || '')}</div></div>${r ? res(r) : ''}</a>`; }).join('')}</div>`;
    }
    d.className = 'drawer open';
    d.innerHTML = `<div class="scrim"></div><div class="panel" role="dialog" aria-modal="true">${S.drawer.length > 1 ? `<button class="btn" type="button" id="dback">${ic('arrowL')}Back</button>` : ''}
      <button class="btn close" type="button" id="dclose" aria-label="Close">${ic('x')}</button><div style="margin-top:${S.drawer.length > 1 ? 12 : 26}px">${h}</div></div>`;
    const close = () => { S.drawer = []; if (location.hash.startsWith('#metric=')) history.replaceState(null, '', `#${S.view}`); drawer(); };
    $('.scrim', d).addEventListener('click', close); $('#dclose', d).addEventListener('click', close);
    if ($('#dback', d)) $('#dback', d).addEventListener('click', () => { S.drawer.pop(); drawer(); });
    if (top2.type === 'metric') {
      const m = MET[top2.id];
      $$('[data-dbk]', d).forEach((b) => b.addEventListener('click', () => { const x = m.breakdown[+b.dataset.dbk]; S.drawer.push({ type: 'list', title: x.label, sub: vname(m.variant), rows: x.rows, run: m.run || PRE }); drawer(); }));
      if ($('#dall', d)) $('#dall', d).addEventListener('click', () => { S.drawer.push({ type: 'list', title: m.headline, sub: vname(m.variant), rows: m.rows, run: m.run || PRE }); drawer(); });
    }
    $$('.rows a', d).forEach((a) => a.addEventListener('click', () => { S.drawer = []; }));
    proofLinks(d, (lv) => { S.drawer.push(lv); drawer(); });
    if ($('#drows', d)) $('#drows', d).addEventListener('click', () => { const c = CHK[top2.id]; S.drawer.push({ type: 'list', title: c.id, sub: c.description, rows: c.rows.ids.filter((id) => IDX[c.rows.run] && IDX[c.rows.run][id]), run: c.rows.run }); drawer(); });
  }
  function proofDrawer(t) {  // a check: expected, observed, evidence; an experiment: its design and checks; a claim: its chain
    const dl = (rows) => `<dl class="kvl pv">${rows.filter(([, v]) => v != null && v !== '').map(([k, v]) => `<dt>${esc(k)}</dt><dd>${v}</dd>`).join('')}</dl>`;
    const checksTable = (ids) => `<div class="twrap"><table class="t"><tbody>${ids.map((id) => { const c = CHK[id] || {}; return `<tr class="link" data-chk="${esc(id)}"><td><b>${esc(id)}</b><div class="small">${md(c.description || '')}</div></td><td class="mono small">${esc(c.expected || '')}</td><td><b>${esc(c.actual ?? '')}</b></td><td>${fdPill(c)}</td></tr>`; }).join('')}</tbody></table></div>`;
    if (t.type === 'check') { const c = CHK[t.id]; if (!c) return '';
      const f = (E.facts || {})[c.fact] || {};
      return `<span class="lbl">${esc(c.experiment)} · ${esc(c.kind)}</span><h2>${esc(c.id)}</h2><p>${fdPill(c)} <span class="small muted">status ${esc(c.status)}</span></p><p class="lead">${md(c.description)}</p>
        ${dl([['Fact', `<span class="mono">${esc(c.fact)}</span>`], ['Expected', `<span class="mono">${esc(c.expected)}</span>`], ['Observed', `<b>${esc(c.actual)}</b>`], ['Threshold', c.threshold_source ? esc(c.threshold_source) : null],
          ['Derivation', f.derivation ? md(f.derivation) : null], ['Frozen', esc(f.freeze || (E.provenance || {}).freeze || '')]])}
        <div class="lbl" style="margin:16px 0 6px">Evidence</div><ul class="evl">${(c.evidence || []).map((e) => `<li><span class="mono">${esc(e.path)}</span>${e.selector ? ` <span class="muted">→ ${esc(e.selector)}</span>` : ''}${e.fact ? `<div class="small muted">fact ${esc(e.fact)}</div>` : ''}</li>`).join('')}</ul>
        ${c.rows && c.rows.count ? `<button class="btn" type="button" id="drows" style="margin-top:12px">${fmt(c.rows.count)} rows · ${esc(c.rows.run)}${ic('arrowR')}</button>` : ''}`; }
    if (t.type === 'experiment') { const x = EXP[t.id]; if (!x) return '';
      return `<span class="lbl">${esc(x.id)}</span><h2>${esc(x.title)}</h2><p>${fdPill(x)} <span class="small muted">result ${esc(x.result)}</span></p><p class="lead">${md(x.question || '')}</p>
        ${dl([['Claim', md(x.claim || '')], ['Hypothesis', md(x.hypothesis || '')], ['Setup', md(x.setup || '')], ['Variable', md(x.variable || '')], ['Invariant', md(x.invariant || '')]])}
        <div class="lbl" style="margin:16px 0 6px">Checks</div>${checksTable(x.checks)}
        ${(x.limitations || []).length ? `<div class="lbl" style="margin:16px 0 6px">Limitations</div><ul>${x.limitations.map((l) => `<li class="small">${md(l)}</li>`).join('')}</ul>` : ''}`; }
    const c = CLM[t.id]; if (!c) return '';
    return `<span class="lbl">${esc(c.id)} · ${esc(c.type)}</span><h2>${md(c.statement)}</h2><p>${stPill(c.verdict)}</p>
      ${dl([['Where', where(c.article)], ['Experiments', (c.experiments || []).map((x) => `<a href="#" data-exp="${esc(x)}">${esc(x)} · ${esc((EXP[x] || {}).title || '')}</a>`).join('<br>')], ['Rests on', c.rests_on ? md(c.rests_on) : null],
        ['Evidence', (c.evidence || []).map((p) => `<span class="mono">${esc(p)}</span>`).join('<br>')]])}
      ${(c.checks || []).length ? `<div class="lbl" style="margin:16px 0 6px">Checks</div>${checksTable(c.checks)}` : ''}`;
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
