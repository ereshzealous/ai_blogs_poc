// Screenshot the Lab Console's views and report script errors:  node tools/shoot_console.mjs <outdir> [hash ...]
import { chromium } from "../../layered_architecture/diagrams/generator/node_modules/playwright-core/index.mjs";
import path from "node:path";
const root = path.resolve(path.dirname(new URL(import.meta.url).pathname), "..");
const [out, ...views] = process.argv.slice(2);
const browser = await chromium.launch({ channel: "chrome", headless: true });
const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
const errors = [];
page.on("pageerror", (e) => errors.push(String(e)));
page.on("console", (m) => { if (m.type() === "error") errors.push(m.text()); });
const url = "file://" + path.join(root, "results/lab-console.html");
for (const v of views.length ? views : ["overview"]) {
  await page.goto(url + "#" + v);
  await page.waitForTimeout(700);
  await page.screenshot({ path: path.join(out, v.replace(/[^a-z0-9-]/gi, "_") + ".png"), fullPage: true });
}
console.log(errors.length ? "ERRORS:\n" + errors.join("\n") : "no script errors");
await browser.close();
