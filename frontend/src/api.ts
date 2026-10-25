import { createClient } from "@supabase/supabase-js";

export const API_URL = (import.meta.env.VITE_API_URL ?? "https://medtrace-et.onrender.com").replace(
  /\/$/,
  "",
);

export const SUPABASE_URL =
  import.meta.env.VITE_SUPABASE_URL ?? "https://qzhumrpdwqkleilqdmbl.supabase.co";
export const SUPABASE_ANON_KEY =
  import.meta.env.VITE_SUPABASE_ANON_KEY ??
  "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InF6aHVtcnBkd3FrbGVpbHFkbWJsIiwicm9sZSI6ImFub24iLCJpYXQiOjE3OTI4ODc3MzcsImV4cCI6MjEwODQ2MzczN30.c7WMDFzD4S2XAGWSuQIgf3NzppWejoxdg-1jqESj-vA";
export const supabase = createClient(SUPABASE_URL, SUPABASE_ANON_KEY);

export type Flag = {
  code: string;
  severity: "info" | "warning" | "critical";
  message: string;
  clone_indicator: boolean;
  details?: Record<string, unknown>;
};

export type Product = {
  valid: boolean;
  gtin: string | null;
  serial: string | null;
  batch: string | null;
  expiry: string | null;
  sscc: string | null;
  days_to_expiry: number | null;
  errors: { code: string; message: string }[];
  warnings: { code: string; message: string }[];
};

export type ScanResult = {
  event_id: string;
  verdict: "PASS" | "WARN" | "FAIL";
  clone_suspected: boolean;
  site_id: string | null;
  flags: Flag[];
  product: Product;
  visual: { status: string; similarity: number | null } | null;
  travel: {
    legs: {
      prior_site_id: string | null;
      distance_km: number;
      speed_kmh: number;
      impossible: boolean;
    }[];
  } | null;
  audit: { pk: string; seq: number; record_hash: string };
  alert_sent: boolean;
};

export type AuditEvent = {
  seq: number;
  event_id: string;
  scanned_at: string;
  event_type: string;
  site_id?: string;
  verdict: string;
  location?: { lat: number; lon: number };
  flags?: Flag[];
  record_hash: string;
};

export type History = {
  identity: string;
  truncated?: boolean;
  scan_count: number;
  chain: { valid: boolean; reason?: string; broken_at_seq?: number };
  events: AuditEvent[];
};

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

/** Retry only read-only operations: a lost POST /scan response may already have committed. */
export async function api<T>(
  path: string,
  init: RequestInit = {},
  token?: string | null,
  attempt = 0,
): Promise<T> {
  const headers = new Headers(init.headers);
  headers.set("Content-Type", "application/json");
  if (token) headers.set("Authorization", `Bearer ${token}`);
  const controller = new AbortController();
  const abort = () => controller.abort();
  init.signal?.addEventListener("abort", abort, { once: true });
  if (init.signal?.aborted) controller.abort();
  const timeout = setTimeout(() => controller.abort(), 90000);
  const retryable = (init.method ?? "GET") === "GET" || path === "/parse";
  try {
    const res = await fetch(API_URL + path, { ...init, headers, signal: controller.signal });
    if (retryable && attempt === 0 && [502, 503, 504].includes(res.status))
      return api<T>(path, init, token, 1);
    const text = await res.text();
    let body: unknown;
    try {
      body = text ? JSON.parse(text) : null;
    } catch {
      throw new ApiError(res.status, "requestFailed");
    }
    if (!res.ok)
      throw new ApiError(res.status, res.status === 401 ? "sessionExpired" : "requestFailed");
    return body as T;
  } catch (error) {
    if (error instanceof ApiError) throw error;
    if (init.signal?.aborted) throw error;
    if (retryable && attempt === 0) return api<T>(path, init, token, 1);
    throw new ApiError(0, retryable ? "networkError" : "ambiguous");
  } finally {
    clearTimeout(timeout);
    init.signal?.removeEventListener("abort", abort);
  }
}

export async function currentToken(): Promise<string | null> {
  const { data } = await supabase.auth.getSession();
  return data.session?.access_token ?? null;
}
