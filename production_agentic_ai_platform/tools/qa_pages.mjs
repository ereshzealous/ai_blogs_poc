// Rendered QA for the two HTML editions (playwright-core from the series tooling, local Chrome).
//   node tools/qa_pages.mjs            -> qa/screens/*.png and qa/page-checks.json
// Checks per page and viewport: console errors, failed requests, horizontal overflow, broken local links and anchors,
// figures rendered, TOC and anchors present, copy buttons present, progress bar moves, print media has no fixed UI.
import { chromium } from "../../series-start-here/diagrams/generator/node_modules/playwright-core/index.mjs";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const OUT = path.join(ROOT, "qa", "screens");
fs.mkdirSync(OUT, { recursive: true });
const pages = [["medium", "medium/production-agentic-ai-platform-medium.html"], ["technical", "technical/production-agentic-ai-platform-final-reference-architecture.html"], ["lab", "results/production-agentic-ai-platform-lab.html"],
  ]
  .filter(([, p]) => fs.existsSync(path.join(ROOT, p)));
const viewports = { desktop: { width: 1440, height: 900 }, tablet: { width: 834, height: 1112 }, mobile: { width: 390, height: 844 } };
const browser = await chromium.launch({ channel: "chrome", headless: true });
const results = [];
for (const [name, rel] of pages) {
  for (const [vp, size] of Object.entries(viewports)) {
    const ctx = await browser.newContext({ viewport: size, colorScheme: "light", deviceScaleFactor: vp === "mobile" ? 2 : 1 });
    const page = await ctx.newPage();
    const errors = [], failed = [];
    page.on("console", (m) => { if (m.type() === "error") errors.push(m.text()); });
    page.on("pageerror", (e) => errors.push(String(e)));
    page.on("requestfailed", (r) => failed.push(r.url()));
    const file = path.join(ROOT, rel);
    await page.goto("file://" + file, { waitUntil: "load" });
    await page.evaluate(() => document.fonts.ready);
    const r = await page.evaluate(() => {
      const doc = document.documentElement;
      const overflow = doc.scrollWidth - doc.clientWidth;
      const wide = [...document.querySelectorAll("body *")].filter((e) => {
        const b = e.getBoundingClientRect();
        if (!b.width) return false;
        // inside a horizontal scroller the reader can reach it; under overflow:hidden it would be cut off, so that still counts
        let scrolls = false;
        for (let s = e.parentElement; s && s !== document.body && !scrolls; s = s.parentElement) scrolls = /^(auto|scroll)$/.test(getComputedStyle(s).overflowX);
        const scroller = e.closest("pre, .table-wrap, .zoom, .m-nav, .fig-scroll") || scrolls;
        return !scroller && b.right > doc.clientWidth + 2;
      }).slice(0, 5).map((e) => e.tagName + "." + e.className);
      const ids = new Set([...document.querySelectorAll("[id]")].map((e) => e.id));
      const badAnchors = [...document.querySelectorAll('a[href^="#"]')].map((a) => decodeURIComponent(a.getAttribute("href").slice(1)))
        .filter((h) => h && !ids.has(h));
      const local = [...document.querySelectorAll("a[href]")].map((a) => a.getAttribute("href")).filter((h) => !/^(https?:|#|mailto:)/.test(h));
      const imgsMissingAlt = [...document.querySelectorAll("img:not([alt])")].length;
      const svgsNoLabel = [...document.querySelectorAll(".fig svg")].filter((s) => !s.getAttribute("aria-label")).length;
      const heads = [...document.querySelectorAll("h1,h2,h3,h4")].map((h) => +h.tagName[1]);
      let skip = 0; for (let i = 1; i < heads.length; i++) if (heads[i] - heads[i - 1] > 1) skip++;
      return { overflow, wide, badAnchors, local, figures: document.querySelectorAll(".fig svg").length, toc: document.querySelectorAll(".m-nav a").length,
        copyButtons: document.querySelectorAll(".hai-copy").length, codeBlocks: document.querySelectorAll(".m-body pre").length,
        anchors: document.querySelectorAll(".hai-anchor").length, cites: document.querySelectorAll(".hai-cite").length, imgsMissingAlt, svgsNoLabel,
        headingSkips: skip, h1: document.querySelectorAll("h1").length };
    });
    const brokenLocal = r.local.filter((h) => !fs.existsSync(path.resolve(path.dirname(file), h.split("#")[0])));
    await page.evaluate(() => window.scrollTo(0, document.documentElement.scrollHeight / 2));
    await page.waitForTimeout(150);
    const progress = await page.evaluate(() => { const p = document.querySelector(".hai-progress"); return p ? parseFloat(p.style.width) : -1; });
    await page.evaluate(() => window.scrollTo(0, 0));
    await page.screenshot({ path: path.join(OUT, `${name}-${vp}-top.png`) });
    const firstFig = await page.$(".m-body .fig");
    if (firstFig) { await firstFig.scrollIntoViewIfNeeded(); await page.waitForTimeout(100); await page.screenshot({ path: path.join(OUT, `${name}-${vp}-figure.png`) }); }
    const proof = await page.$(".m-body figure.proof");
    if (proof && vp !== "tablet") { await proof.scrollIntoViewIfNeeded(); await page.screenshot({ path: path.join(OUT, `${name}-${vp}-proof.png`) }); }
    const pre = await page.$(".m-body pre");
    if (pre && vp !== "tablet") { await pre.scrollIntoViewIfNeeded(); await page.screenshot({ path: path.join(OUT, `${name}-${vp}-code.png`) }); }
    await page.emulateMedia({ media: "print" });
    const printFixed = await page.evaluate(() => [...document.querySelectorAll(".hai-progress,.hai-top,.hai-copy")].filter((e) => getComputedStyle(e).display !== "none").length);
    results.push({ page: name, viewport: vp, errors, failed, ...r, local: undefined, brokenLocal, progressAtHalf: progress, printFixedVisible: printFixed });
    await ctx.close();
  }
}
await browser.close();
fs.writeFileSync(path.join(ROOT, "qa", "page-checks.json"), JSON.stringify(results, null, 1));
for (const r of results) console.log(r.page, r.viewport, JSON.stringify({ errors: r.errors.length, failed: r.failed.length, overflow: r.overflow, wide: r.wide,
  badAnchors: r.badAnchors.length, brokenLocal: r.brokenLocal, figures: r.figures, toc: r.toc, copy: r.copyButtons + "/" + r.codeBlocks, anchors: r.anchors,
  cites: r.cites, progress: Math.round(r.progressAtHalf), printFixed: r.printFixedVisible, skips: r.headingSkips, h1: r.h1 }));
