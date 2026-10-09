// Print the standalone HTML edition to PDF with headless Chrome (playwright-core borrowed from the series' F2 generator).
//   node tools/build_pdf.mjs [in.html] [out.pdf] [--shots dir]
// A4, light theme, print CSS from the page, no browser header/footer. With --shots, also writes screen screenshots.
import { chromium } from "../../layered_architecture/diagrams/generator/node_modules/playwright-core/index.mjs";
import path from "node:path";
import fs from "node:fs";

const args = process.argv.slice(2);
const shotsIdx = args.indexOf("--shots");
const shots = shotsIdx >= 0 ? path.resolve(args.splice(shotsIdx, 2)[1]) : null;
const root = path.resolve(path.dirname(new URL(import.meta.url).pathname), "..");
const file = path.resolve(args[0] ?? path.join(root, "authorization-and-policy-for-ai-agents.html"));
const out = path.resolve(args[1] ?? path.join(root, "authorization-and-policy-for-ai-agents.pdf"));

const browser = await chromium.launch({ channel: "chrome", headless: true });
const ctx = await browser.newContext({ colorScheme: "light", viewport: { width: 1440, height: 1000 }, deviceScaleFactor: 1 });
const page = await ctx.newPage();
await page.goto("file://" + file, { waitUntil: "load" });
await page.evaluate(() => document.fonts.ready);
if (shots) {
  fs.mkdirSync(shots, { recursive: true });
  const h = await page.evaluate(() => document.documentElement.scrollHeight);
  for (let y = 0, i = 0; y < h && i < 60; y += 1000, i++) {
    await page.evaluate((yy) => window.scrollTo(0, yy), y);
    await page.waitForTimeout(60);
    await page.screenshot({ path: path.join(shots, `screen-${String(i).padStart(2, "0")}.png`) });
  }
  const m = await (await browser.newContext({ colorScheme: "light", viewport: { width: 390, height: 844 }, deviceScaleFactor: 2 })).newPage();
  await m.goto("file://" + file, { waitUntil: "load" });
  await m.evaluate(() => document.fonts.ready);
  await m.screenshot({ path: path.join(shots, "mobile-top.png") });
  const overflow = await m.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  console.log("mobile horizontal overflow px:", overflow);
}
await page.emulateMedia({ media: "print" });
await page.waitForTimeout(500);
await page.pdf({ path: out, format: "A4", printBackground: true, preferCSSPageSize: true, displayHeaderFooter: false });
await browser.close();
console.log("wrote", out);
