import { lazy, Suspense, useEffect, useState } from "react";
import type { Session } from "@supabase/supabase-js";
import { supabase } from "./api";
import { ScanPage } from "./ScanPage";
import { LanguageSwitch, useI18n } from "./i18n";
import { LoadBoundary } from "./LoadBoundary";
import { Icon } from "./Icon";
import { ServerStatus } from "./Status";
const HistoryPage = lazy(() => import("./HistoryPage").then((m) => ({ default: m.HistoryPage })));
const ParseTool = lazy(() => import("./ToolsPage").then((m) => ({ default: m.ParseTool })));
const DemoCodes = lazy(() => import("./ToolsPage").then((m) => ({ default: m.DemoCodes })));
const DemoPage = lazy(() => import("./DemoPage"));
const MedicineScene = lazy(() => import("./MedicineScene"));
function Login() {
  const { t } = useI18n();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState(false);
  const [busy, setBusy] = useState(false);
  async function signIn(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(false);
    try {
      const { error } = await supabase.auth.signInWithPassword({ email, password });
      setError(!!error);
      if (!error) setPassword("");
    } catch {
      setError(true);
    } finally {
      setBusy(false);
    }
  }
  return (
    <form className="card login-card" onSubmit={signIn}>
      <span className="eyebrow">{t("workspace")}</span>
      <h2>{t("loginTitle")}</h2>
      <p className="muted">{t("loginHint")}</p>
      <label>
        {t("email")}
        <input
          type="email"
          required
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          autoComplete="username"
          placeholder="name@pharmacy.com"
        />
      </label>
      <label>
        {t("password")}
        <input
          type="password"
          required
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          autoComplete="current-password"
        />
      </label>
      <button className="primary" disabled={busy}>
        {t(busy ? "signingIn" : "signIn")} <span aria-hidden>→</span>
      </button>
      {error && (
        <p className="error" role="alert">
          {t("loginFailed")}
        </p>
      )}
    </form>
  );
}
type Tab = "scan" | "history" | "tools" | "demo";
export function App() {
  const { t } = useI18n();
  const [session, setSession] = useState<Session | null>(null);
  const [tab, setTab] = useState<Tab>("scan");
  const [historyFor, setHistoryFor] = useState<{ gtin: string; serial: string }>();
  const [showTools, setShowTools] = useState(false);
  const [showThree, setShowThree] = useState(false);
  const [theme, setTheme] = useState(
    () =>
      localStorage.getItem("medtrace-theme") ??
      (window.matchMedia?.("(prefers-color-scheme: dark)").matches ? "dark" : "light"),
  );
  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    localStorage.setItem("medtrace-theme", theme);
  }, [theme]);
  useEffect(() => {
    supabase.auth.getSession().then(({ data }) => {
      setSession(data.session);
      if (data.session && !data.session.user.app_metadata?.site_id) setTab("history");
    });
    const { data } = supabase.auth.onAuthStateChange((_event, s) => {
      setSession(s);
      if (_event === "SIGNED_IN" && s && !s.user.app_metadata?.site_id) setTab("history");
      if (!s) {
        setHistoryFor(undefined);
        setTab("scan");
      }
    });
    return () => data.subscription.unsubscribe();
  }, []);
  const site = session?.user.app_metadata?.site_id as string | undefined;
  return (
    <>
      <a className="skip" href="#main">
        {t("skip")}
      </a>
      <header className="topbar">
        <a className="wordmark" href="/">
          <img src="/logo.svg" alt="" width="36" height="36" />
          {t("brand")}
          <span className="wordmark-dot" />
        </a>
        <div className="header-actions">
          <LanguageSwitch />
          <button
            className="theme-button"
            aria-label={t(theme === "light" ? "dark" : "light")}
            onClick={() => setTheme(theme === "light" ? "dark" : "light")}
          >
            {theme === "light" ? "☾" : "☀"}
          </button>
          {session && (
            <button className="signout" onClick={() => supabase.auth.signOut()}>
              {t("signOut")}
            </button>
          )}
        </div>
      </header>
      <div className="statusbar">
        <span>{session ? (site ?? t("inspector")) : t("tagline")}</span>
        <ServerStatus />
      </div>
      <main id="main">
        <LoadBoundary key={tab}>
          <Suspense fallback={<p role="status">{t("loading")}</p>}>
            {tab === "demo" ? (
              <DemoPage onClose={() => setTab("scan")} />
            ) : !session ? (
              <>
                <div className="welcome-grid">
                  <section className="welcome">
                    <span className="eyebrow">{t("workspace")}</span>
                    <h1>{t("welcome")}</h1>
                    <p>{t("intro")}</p>
                    <div className="pack-illustration" aria-hidden>
                      <div className="pack-top">MEDTRACE</div>
                      <div className="pack-cross">+</div>
                      <div className="pack-lines" />
                      <div className="pack-code">▦</div>
                      <span>ET / 001</span>
                    </div>
                    <button className="secondary" onClick={() => setTab("demo")}>
                      {t("demo")} <Icon name="arrow" />
                    </button>
                  </section>
                  <Login />
                </div>
                <section className="quick-tools">
                  <button
                    className="tool-button"
                    onClick={() => setShowTools(!showTools)}
                    aria-expanded={showTools}
                  >
                    {t("parseTitle")} <Icon name="arrow" />
                  </button>
                  <button
                    className="tool-button"
                    onClick={() => setShowThree(!showThree)}
                    aria-expanded={showThree}
                  >
                    {t("loadThree")} <span aria-hidden>◇</span>
                  </button>
                </section>
                {showTools && <ParseTool />}
                {showThree && <MedicineScene />}
              </>
            ) : tab === "scan" ? (
              <>
                <div className="page-heading">
                  <span className="eyebrow">{site ?? t("inspector")}</span>
                  <h1>{t("scanTitle")}</h1>
                  <p>{t("scanIntro")}</p>
                </div>
                <ScanPage
                  onHistory={(gtin, serial) => {
                    setHistoryFor({ gtin, serial });
                    setTab("history");
                  }}
                />
              </>
            ) : tab === "history" ? (
              <HistoryPage initial={historyFor} inspector={!site} />
            ) : (
              <>
                <ParseTool />
                <DemoCodes />
                <button className="secondary" onClick={() => setShowThree(!showThree)}>
                  {t("loadThree")}
                </button>
                {showThree && <MedicineScene />}
              </>
            )}
          </Suspense>
        </LoadBoundary>
        <footer>
          <span className="footer-brand">{t("brand")}</span>
          <p>{t("footer")}</p>
          <small>{t("offlineHint")}</small>
        </footer>
      </main>
      {session && (
        <nav aria-label={t("workspace")}>
          {(["scan", "history", "demo", "tools"] as Tab[]).map((item) => (
            <button
              key={item}
              aria-current={tab === item ? "page" : undefined}
              className={tab === item ? "active" : ""}
              onClick={() => setTab(item)}
            >
              <Icon name={item} />
              {item === "history" && !site ? t("inspector") : t(item)}
            </button>
          ))}
        </nav>
      )}
    </>
  );
}
