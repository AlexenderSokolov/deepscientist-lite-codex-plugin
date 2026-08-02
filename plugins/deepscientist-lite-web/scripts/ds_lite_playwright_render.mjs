import { createRequire } from "node:module";
import process from "node:process";

const args = process.argv.slice(2);
const value = (name) => args[args.indexOf(name) + 1];
const url = value("--url");
const modulePath = value("--playwright-module");
const timeout = Number(value("--timeout") || "30") * 1000;
if (!url || !modulePath || !Number.isFinite(timeout)) process.exit(64);

const require = createRequire(import.meta.url);
const { chromium } = require(modulePath);
let browser;
try {
  browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();
  await page.goto(url, { waitUntil: "domcontentloaded", timeout });
  await page.locator("body").waitFor({ state: "visible", timeout });
  const text = (await page.locator("body").innerText()).slice(0, 2_000_000);
  process.stdout.write(JSON.stringify({ final_url: page.url(), title: await page.title(), text }));
} catch (error) {
  const message = String(error?.message || "render failed").toLowerCase();
  const category = message.includes("timeout") ? "timeout" : message.includes("net::") ? "network" : "render";
  process.stdout.write(JSON.stringify({ error_category: category }));
  process.exitCode = 1;
} finally {
  if (browser) await browser.close();
}
