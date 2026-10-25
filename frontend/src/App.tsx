import { useEffect, useState } from "react";
import type { Session } from "@supabase/supabase-js";
import { supabase } from "./api";
import { HistoryPage } from "./HistoryPage";
import { ScanPage } from "./ScanPage";
import { DemoCodes, ParseTool } from "./ToolsPage";

function Login() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function signIn(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    const { error } = await supabase.auth.signInWithPassword({ email, password });
    if (error) setError(error.message);
    setBusy(false);
  }

  return (
    <form className="card" onSubmit={signIn}>
      <h3>Pharmacy sign-in</h3>
      <label>Email<input type="email" value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="username" /></label>
      <label>Password<input type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="current-password" /></label>
      <button className="primary" disabled={busy}>{busy ? "Signing in…" : "Sign in"}</button>
      {error && <p className="error">{error}</p>}
    </form>
  );
}

type Tab = "scan" | "history" | "tools";

export function App() {
  const [session, setSession] = useState<Session | null>(null);
  const [tab, setTab] = useState<Tab>("scan");
  const [historyFor, setHistoryFor] = useState<{ gtin: string; serial: string }>();

  useEffect(() => {
    supabase.auth.getSession().then(({ data }) => setSession(data.session));
    const { data } = supabase.auth.onAuthStateChange((_event, s) => setSession(s));
    return () => data.subscription.unsubscribe();
  }, []);

  const site = (session?.user.app_metadata as { site_id?: string } | undefined)?.site_id;

  return (
    <>
      <header>
        <h1>MedTrace<span>-ET</span></h1>
        {session && (
          <div className="who">
            <span>{site ?? "Inspector"}</span>
            <button className="link" onClick={() => supabase.auth.signOut()}>Sign out</button>
          </div>
        )}
      </header>
      <main>
        {!session ? (
          <>
            <Login />
            <ParseTool />
            <DemoCodes />
          </>
        ) : tab === "scan" ? (
          <ScanPage onHistory={(gtin, serial) => { setHistoryFor({ gtin, serial }); setTab("history"); }} />
        ) : tab === "history" ? (
          <HistoryPage initial={historyFor} />
        ) : (
          <>
            <ParseTool />
            <DemoCodes />
          </>
        )}
      </main>
      {session && (
        <nav>
          {(["scan", "history", "tools"] as Tab[]).map((t) => (
            <button key={t} className={tab === t ? "active" : ""} onClick={() => setTab(t)}>
              {t === "scan" ? "📷 Scan" : t === "history" ? "🗺 History" : "🧰 Tools"}
            </button>
          ))}
        </nav>
      )}
    </>
  );
}
