// Print an HTML edition to PDF with headless Chrome (needs diagrams/generator/node_modules for playwright-core).
//   node tools/build_pdf.mjs headless-ai.html headless-ai.pdf
import { chromium } from "../diagrams/generator/node_modules/playwright-core/index.mjs";
import path from "node:path";

const [file, out] = process.argv.slice(2).map((p) => path.resolve(p));
const browser = await chromium.launch({ channel: "chrome", headless: true });
const page = await (await browser.newContext({ colorScheme: "light" })).newPage();
await page.goto("file://" + file, { waitUntil: "networkidle" });
await page.evaluate(() => document.fonts.ready);
await page.waitForTimeout(1500);
// Trailing whitespace after the last element can spill into an empty page; trim the page's bottom padding.
await page.addStyleTag({ content: "@page { size: A4; } .shell { padding-block-end: 8px !important; } footer { margin: 4px 0 0 !important; padding: 2px 0 0 !important; font-size: 10px !important; } main > footer { display: none !important; } #references ~ ul li, #references ~ p { font-size: 12.5px !important; line-height: 1.4 !important; margin: 2px 0 !important; }" });
await page.waitForTimeout(200);
await page.pdf({ path: out, format: "A4", printBackground: true,
                 margin: { top: "14mm", bottom: "14mm", left: "12mm", right: "12mm" } });
await browser.close();
console.log("wrote", out);
