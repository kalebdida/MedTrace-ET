import { api, SUPABASE_URL, SUPABASE_ANON_KEY, type ScanResult, type History } from "./api";
import { createClient } from "@supabase/supabase-js";
import { DEMO_GTIN, freshSerial, pharmaBarcode } from "./samples";
export type DemoCredentials = { adama: string; dessie: string };
export type DemoState = {
  step: number;
  serial: string;
  adama?: ScanResult;
  dessie?: ScanResult;
  history?: History;
  error?: string;
};
export type DemoDependencies = {
  signIn: (city: "adama" | "dessie", password: string) => Promise<{ token: string; site?: string }>;
  request: typeof api;
  now: () => Date;
  serial: () => string;
};
export function demoDependencies(): DemoDependencies {
  // Separate non-persistent client: a walkthrough never replaces the pharmacist's normal session.
  const client = createClient(SUPABASE_URL, SUPABASE_ANON_KEY, {
    auth: {
      persistSession: false,
      autoRefreshToken: false,
      detectSessionInUrl: false,
      storageKey: "medtrace-demo-memory",
    },
  });
  return {
    signIn: async (city, password) => {
      const { data, error } = await client.auth.signInWithPassword({
        email: `${city}@medtrace.demo`,
        password,
      });
      if (error || !data.session) throw new Error("loginFailed");
      return { token: data.session.access_token, site: data.user?.app_metadata?.site_id };
    },
    request: api,
    now: () => new Date(),
    serial: freshSerial,
  };
}
export class DemoRun {
  state: DemoState;
  private tokens: Partial<Record<"adama" | "dessie", string>> = {};
  private busy = false;
  private controller = new AbortController();
  private time: Date;
  constructor(private dependencies: DemoDependencies) {
    this.state = { step: 0, serial: dependencies.serial() };
    this.time = dependencies.now();
  }
  dispose() {
    this.controller.abort();
    this.tokens = {};
  }
  async next(passwords: DemoCredentials): Promise<DemoState> {
    if (this.busy || this.state.error || this.state.step >= 5 || this.controller.signal.aborted)
      return this.state;
    this.busy = true;
    try {
      const step = this.state.step;
      if (step === 0 || step === 2) {
        const city = step === 0 ? "adama" : "dessie";
        const auth = await this.dependencies.signIn(city, passwords[city]);
        if (auth.site !== (city === "adama" ? "PH-ADAMA-001" : "PH-DESSIE-007"))
          throw new Error("demoSiteError");
        if (this.controller.signal.aborted) return this.state;
        this.tokens[city] = auth.token;
      } else if (step === 1 || step === 3) {
        const city = step === 1 ? "adama" : "dessie";
        const body = {
          barcode: pharmaBarcode(this.state.serial),
          event_type: city === "adama" ? "receive" : "verify",
          scanned_at: new Date(
            this.time.getTime() - (city === "adama" ? 50 * 60 * 1000 : 0),
          ).toISOString(),
          location:
            city === "adama"
              ? { lat: 8.54, lon: 39.27, accuracy_m: 25 }
              : { lat: 11.13, lon: 39.6333, accuracy_m: 30 },
        };
        this.state[city] = await this.dependencies.request<ScanResult>(
          "/scan",
          { method: "POST", body: JSON.stringify(body), signal: this.controller.signal },
          this.tokens[city],
        );
      } else {
        await this.recoverHistory();
        if (
          !this.state.history?.chain.valid ||
          this.state.history.scan_count !== 2 ||
          this.state.adama?.verdict !== "PASS" ||
          this.state.dessie?.verdict !== "FAIL" ||
          !this.state.dessie.flags.some((f) => f.code === "IMPOSSIBLE_TRAVEL")
        )
          throw new Error("demoUnexpected");
      }
      this.state = { ...this.state, step: step + 1 };
    } catch (e) {
      this.state = { ...this.state, error: e instanceof Error ? e.message : "requestFailed" };
    } finally {
      this.busy = false;
    }
    return this.state;
  }
  async recoverHistory() {
    const q = new URLSearchParams({ gtin: DEMO_GTIN, serial: this.state.serial });
    this.state.history = await this.dependencies.request<History>(
      `/history?${q}`,
      { signal: this.controller.signal },
      this.tokens.dessie ?? this.tokens.adama,
    );
    return this.state.history;
  }
}
