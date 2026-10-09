// Rendered QA for the Lab Console (playwright-core from the series tooling, local Chrome).
//   node tools/qa_console.mjs          -> qa/console-checks.json
// Opens every view and every scenario page of the published run at desktop/tablet/mobile and checks: no console errors,
// no horizontal overflow, and each scenario page actually shows its scenario.
import { chromium } from "../../series-start-here/diagrams/generator/node_modules/playwright-core/index.mjs";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const RUN = fs.readFileSync(path.join(ROOT, "control_plane_poc/runs/PUBLISHED"), "utf8").trim();
const SCEN = fs.readdirSync(path.join(ROOT, "control_plane_poc/runs", RUN, "scenarios")).sort();
const file = "file://" + path.join(ROOT, "results/lab-console.html");
const browser = await chromium.launch({ channel: "chrome", headless: true });
const results = [];
for (const [vp, width, height] of [["desktop", 1440, 900], ["tablet", 834, 1112], ["mobile", 390, 844]]) {
  const page = await browser.newPage({ viewport: { width, height } });
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e)));
  page.on("console", (m) => { if (m.type() === "error") errors.push(m.text()); });
  await page.goto(file, { waitUntil: "load" });
  await page.waitForTimeout(400);
  const views = await page.evaluate(() => [...document.querySelectorAll('a[href^="#"]')].map((a) => a.getAttribute("href").slice(1)).filter(Boolean));
  const targets = [...new Set(views), ...SCEN.map((s) => `row=${RUN}/${s}`)];
  const bad = [];
  for (const h of targets) {
    await page.evaluate((x) => { location.hash = x; }, h);
    await page.waitForTimeout(60);
    const r = await page.evaluate(() => ({ ov: document.documentElement.scrollWidth - document.documentElement.clientWidth, txt: document.body.innerText }));
    if (r.ov > 2) bad.push(`${h}: overflow ${r.ov}px`);
    else if (h.startsWith("row=") && !r.txt.includes(h.split("/").pop())) bad.push(`${h}: scenario not shown`);
  }
  results.push({ viewport: vp, errors, pages: targets.length, bad });
  console.log(vp, JSON.stringify({ errors: errors.length, pages: targets.length, bad }));
  await page.close();
}
await browser.close();
fs.writeFileSync(path.join(ROOT, "qa", "console-checks.json"), JSON.stringify(results, null, 1));
