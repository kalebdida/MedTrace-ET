import { test, expect, type Page } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

async function mockServices(page: Page, alertsMode: "list" | "501" | "403" = "list") {
  let serial = "DEMO0001";
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
    const url = new URL(route.request().url());
    const path = url.pathname;
    if (path === "/health") {
      await route.fulfill({ json: { status: "ok" } });
      return;
    }
    if (path === "/alerts") {
      if (alertsMode === "501") {
        await route.fulfill({ status: 501, json: { error: "Not implemented" } });
        return;
      }
      if (alertsMode === "403") {
        await route.fulfill({ status: 403, json: { error: "Forbidden" } });
        return;
      }
      const before = url.searchParams.get("before");
      if (before) {
        await route.fulfill({
          json: {
            alerts: [
              {
                event_id: "alert-older-1",
                gtin: "09506000134352",
                serial: "DEMO0099",
                site_id: "PH-BAHIR-003",
                prior_site_id: "PH-ADAMA-001",
                distance_km: 368,
                speed_kmh: 412,
                scanned_at: "2026-10-24T14:20:00Z",
                verdict: "FAIL",
              },
            ],
            next_before: null,
          },
        });
        return;
      }
      await route.fulfill({
        json: {
          alerts: [
            {
              event_id: "alert-latest-1",
              gtin: "09506000134352",
              serial: "DEMO0001",
              site_id: "PH-DESSIE-007",
              prior_site_id: "PH-ADAMA-001",
              distance_km: 291,
              speed_kmh: 349,
              scanned_at: "2026-10-25T09:50:00Z",
              verdict: "FAIL",
            },
          ],
          next_before: "2026-10-25T09:50:00Z",
        },
      });
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
              details: {
                prior_event_id: "event-1",
                prior_site_id: "PH-ADAMA-001",
                distance_km: 290.73,
                hours: 0.8333,
                speed_kmh: 348.8,
              },
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
        travel: fail
          ? {
              legs: [
                {
                  prior_site_id: "PH-ADAMA-001",
                  distance_km: 290.73,
                  speed_kmh: 348.8,
                  impossible: true,
                },
              ],
            }
          : null,
        alert_sent: fail,
        audit: { seq: count, pk: "demo", record_hash: "0123456789abcdef".repeat(4) },
      };
      records.push({
        ...result,
        seq: count,
        scanned_at: body.scanned_at,
        event_type: body.event_type,
        location: body.location,
        record_hash: result.audit.record_hash,
      });
      await route.fulfill({ json: result });
      return;
    }
    if (path === "/history") {
      const qSerial = url.searchParams.get("serial") ?? serial;
      if (qSerial === "TEST") {
        await route.fulfill({
          json: {
            identity: qSerial,
            scan_count: 0,
            chain: { valid: true },
            events: [],
          },
        });
        return;
      }
      const eventsToReturn =
        records.length > 0
          ? records
          : [
              {
                seq: 1,
                event_id: "event-1",
                scanned_at: "2026-10-25T09:00:00Z",
                event_type: "receive",
                site_id: "PH-ADAMA-001",
                verdict: "PASS",
                location: { lat: 8.54, lon: 39.27 },
                flags: [],
                record_hash: "517e8e9d0123456789abcdef01234567",
              },
              {
                seq: 2,
                event_id: "event-2",
                scanned_at: "2026-10-25T09:50:00Z",
                event_type: "verify",
                site_id: "PH-DESSIE-007",
                verdict: "FAIL",
                location: { lat: 11.13, lon: 39.6333 },
                flags: [
                  {
                    code: "IMPOSSIBLE_TRAVEL",
                    severity: "critical",
                    message:
                      "This serial was also scanned 291 km away at site PH-ADAMA-001, 50 min apart.",
                    clone_indicator: true,
                    details: { prior_event_id: "event-1" },
                  },
                ],
                record_hash: "5dd331bc0123456789abcdef01234567",
              },
            ];
      await route.fulfill({
        json: {
          identity: qSerial,
          scan_count: eventsToReturn.length,
          chain: { valid: true },
          events: eventsToReturn,
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
  await page.addInitScript(() => {
    Object.defineProperty(navigator, "hardwareConcurrency", { value: 8, configurable: true });
  });
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
  await expect(page.getByTestId("impossible-journey")).toBeVisible();
  await page.screenshot({ path: "docs/screenshots/demo-fail-mobile.png", fullPage: true });
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
  await page.getByRole("button", { name: /Open camera/ }).click();
  await expect(page.getByText(/Camera unavailable/)).toBeVisible();
  await page.getByRole("button", { name: "Use typed barcode" }).click();
  await expect(page.getByRole("textbox", { name: /Barcode/ })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});

test("inspector account lists recent clone alerts, paginates with before, and opens pack history", async ({
  page,
}) => {
  await mockServices(page, "list");
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.goto("/");
  await page.getByLabel("Email address").fill("inspector@medtrace.demo");
  await page.getByLabel("Password", { exact: true }).fill("fixture-only");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Inspect a medicine’s journey" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Recent clone alerts" })).toBeVisible();
  await expect(page.getByText("09506000134352 · DEMO0001")).toBeVisible();
  await page.screenshot({ path: "docs/screenshots/alerts-dashboard-desktop.png", fullPage: true });

  await page.getByRole("button", { name: "Load older alerts" }).click();
  await expect(page.getByText("09506000134352 · DEMO0099")).toBeVisible();

  await page
    .getByRole("button", { name: /Inspect pack history/ })
    .first()
    .click();
  await expect(page.getByText("Audit chain intact", { exact: true })).toBeVisible();
  await expect(page.locator(".leaflet-container")).toBeVisible();
  expect(
    (await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa"]).analyze())
      .violations,
  ).toEqual([]);
  await page.screenshot({ path: "docs/screenshots/inspector-desktop.png", fullPage: true });

  await page.getByLabel("GTIN", { exact: true }).fill("09506000134352");
  await page.getByLabel("Serial", { exact: true }).fill("TEST");
  await page.getByRole("button", { name: /Look up pack/ }).click();
  await expect(page.getByText("No scans recorded for this pack.")).toBeVisible();
});

test("inspector account shows a clear message when GET /alerts returns 501", async ({ page }) => {
  await mockServices(page, "501");
  await page.goto("/");
  await page.getByLabel("Email address").fill("inspector@medtrace.demo");
  await page.getByLabel("Password", { exact: true }).fill("fixture-only");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(page.getByText(/HTTP 501/)).toBeVisible();
  await expect(page.getByText(/A cross-pack alert feed is not available/).first()).toBeVisible();
});
