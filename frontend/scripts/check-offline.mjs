import { chromium } from "@playwright/test";
// Start `npm run preview -- --port 5174` after `npm run build` first.
const browser = await chromium.launch({
  executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE,
});
try {
  const context = await browser.newContext();
  const page = await context.newPage();
  const heavy = [];
  page.on("request", (r) => {
    if (/Scanner-|CloneMap-|MedicineScene-|bwip-js-/.test(r.url())) heavy.push(r.url());
  });
  await page.goto("http://localhost:5174");
  await page.evaluate(() => globalThis.navigator.serviceWorker.ready);
  await page.reload();
  await context.setOffline(true);
  await page.reload();
  await page.getByRole("button", { name: "Sign in", exact: true }).waitFor();
  if (heavy.length) throw new Error("Heavy optional assets loaded on the initial page");
  console.log(
    "PASS: offline app-shell reload; no scanner, map, 3D or barcode generator loaded initially.",
  );
} finally {
  await browser.close();
}
