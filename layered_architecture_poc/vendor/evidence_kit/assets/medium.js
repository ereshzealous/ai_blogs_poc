/* evidence-kit · Medium reading template: the section navigator (current section highlighted as you read, its
   subsections opened; a drawer on narrow screens) and chart rows that open their measurement in the Lab Console. */
(function () {
  var root = document.documentElement, nav = document.querySelector('.m-nav');
  var con = root.getAttribute('data-console');
  if (con) document.querySelectorAll('.ek-hit[data-metric]').forEach(function (g) {
    g.setAttribute('tabindex', '0'); g.setAttribute('role', 'link');
    g.setAttribute('aria-label', 'Open this measurement in the Lab Console');
    var go = function () { location.href = con + '#metric=' + encodeURIComponent(g.getAttribute('data-metric')); };
    g.addEventListener('click', go);
    g.addEventListener('keydown', function (e) { if (e.key === 'Enter') go(); });
  });
  if (!nav) return;
  var cover = document.querySelector('.m-cover');
  if (cover) {  // the section pane waits until the reader is past the cover page
    document.body.classList.add('has-cover');
    var past = function () { document.body.classList.toggle('past-cover', cover.getBoundingClientRect().bottom < 120); };
    window.addEventListener('scroll', past, { passive: true }); past();
  }
  var links = [].slice.call(nav.querySelectorAll('a[href^="#"]'));
  var heads = links.map(function (a) { return document.getElementById(decodeURIComponent(a.getAttribute('href').slice(1))); });
  var btn = document.querySelector('.m-toc-btn'), scrim = document.querySelector('.m-scrim');
  function close() { document.body.classList.remove('nav-open'); if (btn) btn.setAttribute('aria-expanded', 'false'); }
  if (btn) btn.addEventListener('click', function () {
    var open = document.body.classList.toggle('nav-open'); btn.setAttribute('aria-expanded', String(open));
  });
  if (scrim) scrim.addEventListener('click', close);
  document.addEventListener('keydown', function (e) { if (e.key === 'Escape') close(); });
  links.forEach(function (a) { a.addEventListener('click', close); });
  var current = -1;
  function spy() {
    var y = 110, i = -1;
    for (var k = 0; k < heads.length; k++) { if (heads[k] && heads[k].getBoundingClientRect().top <= y) i = k; else if (heads[k]) break; }
    if (i === current) return;
    current = i;
    links.forEach(function (a, k) { a.classList.toggle('on', k === i); });
    nav.querySelectorAll('li.open').forEach(function (li) { li.classList.remove('open'); });
    if (i < 0) return;
    var li = links[i].closest('li'), top = li.parentElement.closest('li') || li;
    top.classList.add('open');
    var r = links[i].getBoundingClientRect(), n = nav.getBoundingClientRect();
    if (r.top < n.top + 40 || r.bottom > n.bottom - 40) nav.scrollTop += r.top - n.top - n.height / 3;
  }
  var ticking = false;
  window.addEventListener('scroll', function () {
    if (!ticking) { ticking = true; requestAnimationFrame(function () { ticking = false; spy(); }); }
  }, { passive: true });
  spy();
})();
