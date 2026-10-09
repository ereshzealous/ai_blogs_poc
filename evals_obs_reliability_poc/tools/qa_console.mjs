// Rendered QA of the Lab Console: no console errors, every tab renders, a cell opens its run.  -> qa/screens/console-*.png
import { chromium } from "../../series-start-here/diagrams/generator/node_modules/playwright-core/index.mjs";
import path from "node:path";
import fs from "node:fs";
import { fileURLToPath } from "node:url";
const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
fs.mkdirSync(path.join(ROOT, "qa", "screens"), { recursive: true });
const browser = await chromium.launch({ channel: "chrome", headless: true });
const page = await (await browser.newContext({ viewport: { width: 1440, height: 900 } })).newPage();
const errors = [];
page.on("console", (m) => { if (m.type() === "error") errors.push(m.text()); });
page.on("pageerror", (e) => errors.push(String(e)));
await page.goto("file://" + path.join(ROOT, "results", "lab-console.html"));
const out = {};
for (const t of ["overview", "scenarios", "live", "proof", "claims", "mutants", "slice"]) {
  await page.click(`nav.tabs button[data-t="${t}"]`);
  out[t] = await page.evaluate((t) => document.querySelector("#t-" + t).innerText.length, t);
  await page.screenshot({ path: path.join(ROOT, "qa", "screens", `console-${t}.png`) });
}
await page.click(`nav.tabs button[data-t="overview"]`);
await page.click(".grid div.bad");
const opened = await page.evaluate(() => document.querySelector("#run h2").innerText);
fs.writeFileSync(path.join(ROOT, "qa", "console-checks.json"), JSON.stringify({ errors, text_chars: out, cell_opens: opened }, null, 1));
console.log(JSON.stringify({ errors, out, opened }));
await browser.close();
