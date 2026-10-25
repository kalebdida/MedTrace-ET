import { afterEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { ResultCard } from "./ResultCard";
import { api, type ScanResult } from "./api";
import { GS, fromVisible, pharmaBarcode, visible } from "./samples";

const clone: ScanResult = {
  event_id: "e1",
  verdict: "FAIL",
  clone_suspected: true,
  site_id: "PH-DESSIE-007",
  flags: [{ code: "IMPOSSIBLE_TRAVEL", severity: "critical", message: "Scanned 291 km away 50 min apart.", clone_indicator: true }],
  product: { valid: true, gtin: "09506000134352", serial: "DEMO1", batch: "B1", expiry: "2030-12-31", sscc: null, days_to_expiry: 1500, errors: [], warnings: [] },
  visual: null,
  travel: null,
  audit: { pk: "SGTIN#x", seq: 2, record_hash: "abcdef0123456789abcdef" },
  alert_sent: true,
};

afterEach(() => vi.restoreAllMocks());

describe("ResultCard", () => {
  it("shows a clear do-not-dispense verdict for a clone", () => {
    render(<ResultCard result={clone} />);
    expect(screen.getByText(/Do NOT dispense/)).toBeTruthy();
    expect(screen.getByText(/Cloned barcode intercepted; EFDA alert sent/)).toBeTruthy();
    expect(screen.getByText("IMPOSSIBLE TRAVEL")).toBeTruthy();
  });
});

describe("api client", () => {
  it("sends the bearer token and surfaces backend errors", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response('{"error":"Sign-in required"}', { status: 401 }));
    vi.stubGlobal("fetch", fetchMock);
    await expect(api("/scan", { method: "POST", body: "{}" }, "tok")).rejects.toThrow("Sign-in required");
    expect(fetchMock.mock.calls[0][1].headers.Authorization).toBe("Bearer tok");
  });
});

describe("barcode helpers", () => {
  it("keeps GS separators through the visible round-trip", () => {
    const code = pharmaBarcode("S1");
    expect(code).toContain(GS);
    expect(fromVisible(visible(code))).toBe(code);
  });
});
