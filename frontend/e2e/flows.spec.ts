import { test, expect, type Page } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

async function mockServices(page: Page) {
  let serial = "";
  let count = 0;
  const records: Record<string, unknown>[] = [];
  await page.route("**/*.tile.openstreetmap.org/**", (route) => route.abort());
  await page.route("**/auth/v1/**", async (route) => {
    const data = route.request().postDataJSON() as { email: string };
    const city = data.email.startsWith("adama")
      ? "ADAMA"
      : data.email.startsWith("inspector")
        ? "INSPECTOR"
        : "DESSIE";
    const user = {
      id: city,
      aud: "authenticated",
      role: "authenticated",
      email: data.email,
      app_metadata:
        city === "INSPECTOR"
          ? {}
          : { site_id: city === "ADAMA" ? "PH-ADAMA-001" : "PH-DESSIE-007" },
      user_metadata: {},
      created_at: "2026-01-01T00:00:00Z",
    };
    await route.fulfill({
      json: {
        access_token: "fixture-access-token-" + city,
        token_type: "bearer",
        expires_in: 3600,
        refresh_token: "fixture-refresh",
        user,
      },
    });
  });
  await page.route("https://medtrace-et.onrender.com/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path === "/health") {
      await route.fulfill({ json: { status: "ok" } });
      return;
    }
    if (path === "/scan") {
      count++;
      const body = route.request().postDataJSON();
      serial = body.barcode.split("\u001d21")[1];
      const fail = count === 2;
      const flags = fail
        ? [
            {
              code: "IMPOSSIBLE_TRAVEL",
              severity: "critical",
              message: "The same serial travelled between Adama and Dessie in 50 minutes.",
              clone_indicator: true,
              details: { prior_event_id: "event-1" },
            },
          ]
        : [];
      const result = {
        event_id: "event-" + count,
        verdict: fail ? "FAIL" : "PASS",
        clone_suspected: fail,
        flags,
        site_id: fail ? "PH-DESSIE-007" : "PH-ADAMA-001",
        product: {
          gtin: "09506000134352",
          serial,
          batch: "BATCH42",
          expiry: "2030-12-31",
          valid: true,
          errors: [],
          warnings: [],
        },
        visual: null,
        travel: null,
        alert_sent: fail,
        audit: { seq: count, pk: "demo", record_hash: "0123456789abcdef".repeat(4) },
      };
      records.push({
        ...result,
        seq: count,
        scanned_at: body.scanned_at,
        event_type: body.event_type,
        location: body.location,
      });
      await route.fulfill({ json: result });
      return;
    }
    if (path === "/history") {
      await route.fulfill({
        json: {
          identity: serial,
          scan_count: records.length,
          chain: { valid: true },
          events: records,
        },
      });
      return;
    }
    await route.fulfill({
      json: {
        valid: true,
        gtin: "09506000134352",
        serial: "S1",
        batch: "B1",
        expiry: "2030-12-31",
        errors: [],
        warnings: [],
      },
    });
  });
}

test("accessible desktop login, mobile language and theme", async ({ page }) => {
  await mockServices(page);
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.goto("/");
  await expect(page.getByText("Server connected")).toBeVisible();
  expect(
    (await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa"]).analyze())
      .violations,
  ).toEqual([]);
  await page.screenshot({ path: "docs/screenshots/login-desktop.png", fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.getByLabel("Language").selectOption("am");
  await expect(page.getByRole("button", { name: "ይግቡ" })).toBeVisible();
  await page.screenshot({ path: "docs/screenshots/login-amharic-mobile.png", fullPage: true });
  await page.getByLabel("ጨለማ ገጽታ").click();
  expect(
    (await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa"]).analyze())
      .violations,
  ).toEqual([]);
  await page.screenshot({ path: "docs/screenshots/login-dark-mobile.png", fullPage: true });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});

test("guided clone walkthrough: PASS, FAIL and intact history", async ({ page }) => {
  await mockServices(page);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");
  await page.getByRole("button", { name: "Clone demo" }).click();
  await page.getByLabel("Adama demo password").fill("fixture-only");
  await page.getByLabel("Dessie demo password").fill("fixture-only");
  await page.getByRole("button", { name: "Start walkthrough" }).click();
  await page.getByRole("button", { name: "Continue to next step" }).click();
  await expect(page.getByRole("heading", { name: "Checks passed" })).toBeVisible();
  await page.screenshot({ path: "docs/screenshots/demo-pass-mobile.png", fullPage: true });
  await page.getByRole("button", { name: "Continue to next step" }).click();
  await page.getByRole("button", { name: "Continue to next step" }).click();
  await expect(page.getByRole("heading", { name: "Do NOT dispense" })).toBeVisible();
  await page.getByRole("button", { name: "Continue to next step" }).click();
  await expect(page.getByText("Audit chain intact", { exact: true })).toBeVisible();
  await expect(page.locator(".leaflet-container")).toBeVisible();
  expect(
    (await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa"]).analyze())
      .violations,
  ).toEqual([]);
  await page.screenshot({ path: "docs/screenshots/demo-clone-history-mobile.png", fullPage: true });
  expect(await page.evaluate(() => JSON.stringify(localStorage))).not.toContain("fixture-only");
});

test("camera denial leaves a usable typed-code fallback", async ({ page }) => {
  await mockServices(page);
  await page.setViewportSize({ width: 320, height: 720 });
  await page.addInitScript(() => {
    Object.defineProperty(navigator, "mediaDevices", {
      value: { getUserMedia: () => Promise.reject(new DOMException("Denied", "NotAllowedError")) },
    });
  });
  await page.goto("/");
  await page.getByLabel("Email address").fill("adama@medtrace.demo");
  await page.getByLabel("Password", { exact: true }).fill("fixture-only");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await page.getByRole("button", { name: "Open camera" }).click();
  await expect(page.getByText(/Camera unavailable/)).toBeVisible();
  await page.getByRole("button", { name: "Use typed barcode" }).click();
  await expect(page.getByRole("textbox", { name: /Barcode/ })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});

test("inspector account opens honest pack lookup without inventing a feed", async ({ page }) => {
  await mockServices(page);
  await page.goto("/");
  await page.getByLabel("Email address").fill("inspector@medtrace.demo");
  await page.getByLabel("Password", { exact: true }).fill("fixture-only");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Inspect a medicine’s journey" })).toBeVisible();
  await expect(page.getByText(/A cross-pack alert feed is not available/)).toBeVisible();
  await page.getByLabel("GTIN", { exact: true }).fill("09506000134352");
  await page.getByLabel("Serial", { exact: true }).fill("TEST");
  await page.getByRole("button", { name: "Look up pack" }).click();
  await expect(page.getByText("No scans recorded for this pack.")).toBeVisible();
  await page.screenshot({ path: "docs/screenshots/inspector-desktop.png", fullPage: true });
});
