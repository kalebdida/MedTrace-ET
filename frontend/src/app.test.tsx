import { afterEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { ResultCard } from "./ResultCard";
import { api, type ScanResult, type History } from "./api";
import { GS, fromVisible, pharmaBarcode, visible } from "./samples";
import { LanguageProvider, LanguageSwitch, useI18n } from "./i18n";
import { DemoRun, type DemoDependencies } from "./demo";

export const clone: ScanResult = {
  event_id: "e1",
  verdict: "FAIL",
  clone_suspected: true,
  site_id: "PH-DESSIE-007",
  flags: [
    {
      code: "IMPOSSIBLE_TRAVEL",
      severity: "critical",
      message: "Scanned 291 km away 50 min apart.",
      clone_indicator: true,
    },
  ],
  product: {
    valid: true,
    gtin: "09506000134352",
    serial: "DEMO1",
    batch: "B1",
    expiry: "2030-12-31",
    sscc: null,
    days_to_expiry: 1500,
    errors: [],
    warnings: [],
  },
  visual: null,
  travel: null,
  audit: { pk: "SGTIN#x", seq: 2, record_hash: "abcdef0123456789abcdef" },
  alert_sent: true,
};
afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});
describe("ResultCard", () => {
  it.each([
    ["PASS", "Checks passed"],
    ["WARN", "Check before dispensing"],
    ["FAIL", "Do NOT dispense"],
  ] as const)("renders %s with an explicit action", (verdict, title) => {
    render(<ResultCard result={{ ...clone, verdict, clone_suspected: verdict === "FAIL" }} />);
    expect(screen.getByRole("heading", { name: title })).toBeTruthy();
    expect(screen.getByTestId("result").className).toContain(verdict.toLowerCase());
  });
  it("does not claim authenticity or pretend the recipient is EFDA", () => {
    render(<ResultCard result={clone} />);
    expect(screen.getByText("Alert delivered to the configured channel")).toBeTruthy();
    expect(screen.queryByText(/EFDA alert sent/)).toBeNull();
  });
  it("states delivery failure clearly", () => {
    render(<ResultCard result={{ ...clone, alert_sent: false }} />);
    expect(screen.getByText(/report this pack manually/)).toBeTruthy();
  });
});
describe("API client", () => {
  it("attaches token and handles 401 without retrying", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(new Response('{"error":"Sign-in required"}', { status: 401 }));
    vi.stubGlobal("fetch", fetchMock);
    await expect(api("/scan", { method: "POST", body: "{}" }, "tok")).rejects.toMatchObject({
      status: 401,
      message: "sessionExpired",
    });
    expect(fetchMock.mock.calls[0][1].headers.get("Authorization")).toBe("Bearer tok");
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
  it("retries a failed health read once", async () => {
    const fn = vi
      .fn()
      .mockRejectedValueOnce(new TypeError("offline"))
      .mockResolvedValue(new Response('{"status":"ok"}'));
    vi.stubGlobal("fetch", fn);
    await expect(api("/health")).resolves.toEqual({ status: "ok" });
    expect(fn).toHaveBeenCalledTimes(2);
  });
  it("retries cold-start 503 HTML for parse", async () => {
    const fn = vi
      .fn()
      .mockResolvedValueOnce(new Response("<html>Waking</html>", { status: 503 }))
      .mockResolvedValue(new Response('{"valid":true}'));
    vi.stubGlobal("fetch", fn);
    await expect(api("/parse", { method: "POST", body: "{}" })).resolves.toEqual({ valid: true });
    expect(fn).toHaveBeenCalledTimes(2);
  });
  it("never duplicates a write after a lost response", async () => {
    const fn = vi.fn().mockRejectedValue(new TypeError("network"));
    vi.stubGlobal("fetch", fn);
    await expect(api("/scan", { method: "POST", body: "{}" })).rejects.toMatchObject({
      message: "ambiguous",
    });
    expect(fn).toHaveBeenCalledTimes(1);
  });
  it("handles non-JSON errors without a JSON syntax error", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("error", { status: 500 })));
    await expect(api("/scan", { method: "POST" })).rejects.toMatchObject({
      status: 500,
      message: "requestFailed",
    });
  });
});
describe("language switch", () => {
  function Example() {
    const { t } = useI18n();
    return (
      <>
        <LanguageSwitch />
        <p>{t("signIn")}</p>
      </>
    );
  }
  it("changes the main flow, document language, and saved preference", () => {
    render(
      <LanguageProvider>
        <Example />
      </LanguageProvider>,
    );
    fireEvent.change(screen.getByLabelText("Language"), { target: { value: "am" } });
    expect(screen.getByText("ይግቡ")).toBeTruthy();
    expect(document.documentElement.lang).toBe("am");
    expect(localStorage.getItem("medtrace-language")).toBe("am");
  });
});
describe("barcode helpers", () => {
  it("preserves GS separators", () => {
    const code = pharmaBarcode("S1");
    expect(code).toContain(GS);
    expect(fromVisible(visible(code))).toBe(code);
  });
});
describe("demo walkthrough", () => {
  function setup() {
    const history: History = {
      identity: "pack",
      scan_count: 2,
      chain: { valid: true },
      events: [],
    };
    const request = vi
      .fn()
      .mockResolvedValueOnce({ ...clone, verdict: "PASS", clone_suspected: false })
      .mockResolvedValueOnce(clone)
      .mockResolvedValueOnce(history);
    const signIn = vi.fn().mockImplementation(async (city: string) => ({
      token: city + "-token",
      site: city === "adama" ? "PH-ADAMA-001" : "PH-DESSIE-007",
    }));
    const dependencies: DemoDependencies = {
      signIn,
      request: request as typeof api,
      now: () => new Date("2026-10-25T10:00:00Z"),
      serial: () => "DEMO-UNIQUE",
    };
    return { run: new DemoRun(dependencies), request, signIn, dependencies };
  }
  it("uses the same serial, two verified sites and timestamps 50 minutes apart", async () => {
    const { run, request, signIn } = setup();
    for (let i = 0; i < 5; i++)
      await run.next({ adama: "fixture-only-a", dessie: "fixture-only-d" });
    expect(run.state.step).toBe(5);
    expect(run.state.history?.chain.valid).toBe(true);
    expect(signIn.mock.calls.map((c) => c[0])).toEqual(["adama", "dessie"]);
    const first = JSON.parse(request.mock.calls[0][1].body);
    const second = JSON.parse(request.mock.calls[1][1].body);
    expect(first.barcode).toBe(second.barcode);
    expect(Date.parse(second.scanned_at) - Date.parse(first.scanned_at)).toBe(50 * 60 * 1000);
    expect(request.mock.calls[0][2]).toBe("adama-token");
    expect(request.mock.calls[1][2]).toBe("dessie-token");
    expect(first).not.toHaveProperty("site_id");
    run.dispose();
  });
  it("does not retry a failed scan step", async () => {
    const { run, request } = setup();
    request.mockReset().mockRejectedValue(new Error("ambiguous"));
    await run.next({ adama: "a", dessie: "d" });
    await run.next({ adama: "a", dessie: "d" });
    await run.next({ adama: "a", dessie: "d" });
    expect(request).toHaveBeenCalledTimes(1);
    expect(run.state.error).toBe("ambiguous");
    run.dispose();
  });
  it("rejects a demo account with the wrong assigned site", async () => {
    const { dependencies } = setup();
    dependencies.signIn = async () => ({ token: "x", site: "WRONG" });
    const run = new DemoRun(dependencies);
    await run.next({ adama: "a", dessie: "d" });
    expect(run.state.error).toBe("demoSiteError");
    expect(run.state.step).toBe(0);
    run.dispose();
  });
  it("does not describe an unexpected verdict as success", async () => {
    const { run, request } = setup();
    request
      .mockReset()
      .mockResolvedValueOnce({ ...clone, verdict: "WARN" })
      .mockResolvedValueOnce(clone)
      .mockResolvedValueOnce({ scan_count: 2, chain: { valid: true } });
    for (let i = 0; i < 5; i++) await run.next({ adama: "a", dessie: "d" });
    expect(run.state.error).toBe("demoUnexpected");
    run.dispose();
  });
});
