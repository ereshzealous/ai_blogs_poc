// Rendered QA for the S2 Medium edition (playwright-core from the series tooling, local Chrome). Ported from O1+O2.
//   node tools/qa_pages.mjs [screens-dir]   -> screenshots in screens-dir (default qa/screens) and verification/page-checks.json
// Desktop and phone only. Checks per viewport: console errors, failed requests, horizontal overflow, broken local links and anchors,
// figures rendered and labelled, the zoom viewer (opens, scales to a readable size on a phone, pans, closes on Escape),
// the progress bar, and that print media hides the fixed UI.
import { chromium } from "../../series-start-here/diagrams/generator/node_modules/playwright-core/index.mjs";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const OUT = path.resolve(process.argv[2] || path.join(ROOT, "qa", "screens"));
fs.mkdirSync(OUT, { recursive: true });
const SLUG = "enterprise-knowledge-rag";
const pages = [["medium", `medium/${SLUG}-medium.html`]].filter(([, p]) => fs.existsSync(path.join(ROOT, p)));
const viewports = { desktop: { width: 1440, height: 900 }, mobile: { width: 390, height: 844 } };
const browser = await chromium.launch({ channel: "chrome", headless: true });
const results = [];
for (const [name, rel] of pages) {
  for (const [vp, size] of Object.entries(viewports)) {
    const ctx = await browser.newContext({ viewport: size, colorScheme: "light", deviceScaleFactor: vp === "mobile" ? 2 : 1,
      hasTouch: vp === "mobile", isMobile: vp === "mobile" });
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
        const scroller = e.closest("pre, .table-wrap, .zoom, .m-nav, .m-top");
        return !scroller && b.right > doc.clientWidth + 2;
      }).slice(0, 5).map((e) => e.tagName + "." + e.className);
      const ids = new Set([...document.querySelectorAll("[id]")].map((e) => e.id));
      const badAnchors = [...document.querySelectorAll('a[href^="#"]')].map((a) => decodeURIComponent(a.getAttribute("href").slice(1)))
        .filter((h) => h && !ids.has(h));
      const local = [...document.querySelectorAll("a[href]")].map((a) => a.getAttribute("href")).filter((h) => !/^(https?:|#|mailto:)/.test(h));
      const figs = [...document.querySelectorAll(".fig svg")];
      return { overflow, wide, badAnchors, local, figures: figs.length, svgsNoLabel: figs.filter((s) => !s.getAttribute("aria-label")).length,
        figuresOverflowing: figs.filter((s) => s.getBoundingClientRect().right > doc.clientWidth + 2).length,
        zoomButtons: document.querySelectorAll(".fig-zoom").length, scorecards: document.querySelectorAll(".hai-score li").length,
        callouts: document.querySelectorAll(".m-callout").length, h1: document.querySelectorAll("h1").length };
    });
    const brokenLocal = r.local.filter((h) => !fs.existsSync(path.resolve(path.dirname(file), decodeURIComponent(h.split("#")[0]))));
    await page.evaluate(() => window.scrollTo(0, document.documentElement.scrollHeight / 2));
    await page.waitForTimeout(150);
    const progress = await page.evaluate(() => parseFloat(document.querySelector(".hai-progress").style.width));
    await page.evaluate(() => window.scrollTo(0, 0));
    await page.screenshot({ path: path.join(OUT, `${name}-${vp}-top.png`) });
    let viewer = null;
    if (name === "medium") {
      const sc = await page.$(".hai-score");
      if (sc) { await sc.scrollIntoViewIfNeeded(); await page.waitForTimeout(80); await page.screenshot({ path: path.join(OUT, `${name}-${vp}-scorecard.png`) }); }
      const co = await page.$(".m-callout.t-red");
      if (co) { await co.scrollIntoViewIfNeeded(); await page.waitForTimeout(80); await page.screenshot({ path: path.join(OUT, `${name}-${vp}-callout.png`) }); }
      const ol = await page.$(".m-body ol");
      if (ol) { await ol.scrollIntoViewIfNeeded(); await page.waitForTimeout(80); await page.screenshot({ path: path.join(OUT, `${name}-${vp}-rules.png`) }); }
      const fig = await page.$("#fig-gates");
      if (fig) {
        await fig.scrollIntoViewIfNeeded(); await page.waitForTimeout(80);
        await page.screenshot({ path: path.join(OUT, `${name}-${vp}-figure.png`) });
        await page.click("#fig-gates .fig-zoom");
        await page.waitForTimeout(200);
        viewer = await page.evaluate(() => {
          const z = document.querySelector(".zoom"), zin = z.querySelector(".zin"), svg = z.querySelector(".zc svg");
          const before = zin.scrollLeft; zin.scrollLeft = 300; const panned = zin.scrollLeft - before;
          zin.scrollLeft = before;
          return { open: z.classList.contains("on"), contentWidth: Math.round(svg.getBoundingClientRect().width), viewport: window.innerWidth,
            pannable: zin.scrollWidth > zin.clientWidth, panned, bodyLocked: document.documentElement.style.overflow === "hidden" };
        });
        await page.screenshot({ path: path.join(OUT, `${name}-${vp}-viewer.png`) });
        await page.click('.zoom [data-z="in"]'); await page.waitForTimeout(80);
        viewer.afterZoomIn = await page.evaluate(() => Math.round(document.querySelector(".zoom .zc svg").getBoundingClientRect().width));
        await page.keyboard.press("Escape"); await page.waitForTimeout(80);
        viewer.closedOnEscape = await page.evaluate(() => !document.querySelector(".zoom").classList.contains("on"));
      }
    }
    await page.emulateMedia({ media: "print" });
    const printFixed = await page.evaluate(() => [...document.querySelectorAll(".hai-progress,.hai-top,.hai-copy,.fig-zoom,.zoom")]
      .filter((e) => getComputedStyle(e).display !== "none").length);
    results.push({ page: name, viewport: vp, errors, failed, ...r, local: undefined, brokenLocal, progressAtHalf: progress, viewer, printFixedVisible: printFixed });
    await ctx.close();
  }
}
await browser.close();
fs.writeFileSync(path.join(ROOT, "verification", "page-checks.json"), JSON.stringify(results, null, 1));
for (const r of results) console.log(r.page, r.viewport, JSON.stringify({ errors: r.errors.length, failed: r.failed.length, overflow: r.overflow, wide: r.wide,
  badAnchors: r.badAnchors.length, brokenLocal: r.brokenLocal, figures: r.figures, figOverflow: r.figuresOverflowing, zoomBtns: r.zoomButtons,
  score: r.scorecards, callouts: r.callouts, progress: Math.round(r.progressAtHalf), printFixed: r.printFixedVisible, viewer: r.viewer }));
