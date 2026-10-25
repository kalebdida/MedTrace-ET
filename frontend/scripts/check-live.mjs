/** Opt-in real writes. Passwords are read from environment only; output contains no credentials. */
import { chromium } from "@playwright/test";
if (!process.env.ADAMA_PASSWORD || !process.env.DESSIE_PASSWORD)
  throw new Error("Set ADAMA_PASSWORD and DESSIE_PASSWORD in your shell");
const browser = await chromium.launch({
  executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE,
});
try {
  const context = await browser.newContext();
  const page = await context.newPage();
  page.setDefaultTimeout(180000);
  await page.goto(process.env.FRONTEND_URL ?? "http://localhost:5173");
  await page.getByRole("button", { name: "Clone demo", exact: true }).click();
  await page.getByLabel("Adama demo password").fill(process.env.ADAMA_PASSWORD);
  await page.getByLabel("Dessie demo password").fill(process.env.DESSIE_PASSWORD);
  await page.getByRole("button", { name: "Start walkthrough" }).click();
  await page.getByRole("button", { name: "Continue to next step" }).click();
  await page.getByRole("heading", { name: "Checks passed", exact: true }).waitFor();
  console.log("Live Adama PASS confirmed");
  await page.getByRole("button", { name: "Continue to next step" }).click();
  await page.getByRole("button", { name: "Continue to next step" }).click();
  await page.getByRole("heading", { name: "Do NOT dispense", exact: true }).waitFor();
  console.log("Live Dessie FAIL confirmed");
  await page.getByRole("button", { name: "Continue to next step" }).click();
  await page.getByText("Audit chain intact", { exact: true }).waitFor();
  console.log("Live history chain intact confirmed");
  await page
    .getByText("Clone detected. The two scans share one intact audit chain.", { exact: true })
    .waitFor();
} catch {
  console.error(
    "Live verification failed. Check connectivity, credentials and the UI; diagnostic logs are omitted to protect passwords.",
  );
  process.exitCode = 1;
} finally {
  await browser.close();
}
