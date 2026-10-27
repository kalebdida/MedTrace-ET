import { lazy, Suspense, useEffect, useState, type ComponentType } from "react";
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

function shouldAutoLoadHeroThree(): boolean {
  if (typeof window === "undefined") return false;
  if (navigator.onLine === false) return false;
  if (window.matchMedia?.("(prefers-reduced-motion: reduce)").matches) return false;
  const cores = navigator.hardwareConcurrency ?? 8;
  const mem = (navigator as { deviceMemory?: number }).deviceMemory ?? 8;
  if (cores <= 4 || mem <= 2) return false;
  try {
    const canvas = document.createElement("canvas");
    const gl = canvas.getContext("webgl2") || canvas.getContext("webgl");
    if (!gl) return false;
  } catch {
    return false;
  }
  return true;
}

function HeroStaticSvgFallback() {
  const { t } = useI18n();
  return (
    <div className="hero-scanner-stage" data-testid="hero-svg-stage">
      <div className="hero-scanner-hud">
        <span className="scanner-hud-label">{t("heroScannerBadge")}</span>
        <div className="scanner-state-pill" data-state="genuine" aria-hidden="true">
          <span className="scanner-state-icon">
            <Icon name="check" size={14} />
          </span>
          <span>{t("heroStateGenuine")}</span>
        </div>
      </div>
      <div className="hero-svg-fallback">
        <svg
          viewBox="0 0 360 280"
          role="img"
          aria-label="GS1 DataMatrix medicine pack scanner"
          className="pack-svg"
        >
          <defs>
            <linearGradient id="heroPackBg" x1="0" y1="0" x2="1" y2="1">
              <stop offset="0%" stopColor="#0a2926" />
              <stop offset="100%" stopColor="#061816" />
            </linearGradient>
            <linearGradient id="heroLaserLine" x1="0" y1="0" x2="1" y2="0">
              <stop offset="0%" stopColor="#14b8a6" stopOpacity="0" />
              <stop offset="50%" stopColor="#2dd4bf" stopOpacity="1" />
              <stop offset="100%" stopColor="#14b8a6" stopOpacity="0" />
            </linearGradient>
          </defs>
          <rect width="360" height="280" rx="16" fill="url(#heroPackBg)" />
          <g stroke="#5eead41f" strokeWidth="1">
            <line x1="0" y1="56" x2="360" y2="56" />
            <line x1="0" y1="140" x2="360" y2="140" />
            <line x1="0" y1="224" x2="360" y2="224" />
            <line x1="90" y1="0" x2="90" y2="280" />
            <line x1="180" y1="0" x2="180" y2="280" />
            <line x1="270" y1="0" x2="270" y2="280" />
          </g>
          <g transform="translate(86, 22)">
            <polygon points="168,16 192,4 192,206 168,218" fill="#d8e3dd" stroke="#7c988e" />
            <polygon points="0,16 24,4 192,4 168,16" fill="#0f766e" stroke="#5eead4" />
            <rect
              x="0"
              y="16"
              width="168"
              height="202"
              rx="4"
              fill="#f8faf7"
              stroke="#14b8a6"
              strokeWidth="2"
            />
            <rect x="0" y="16" width="168" height="36" rx="3" fill="#0b4f4a" />
            <text
              x="14"
              y="38"
              fill="#ffffff"
              fontSize="11"
              fontWeight="800"
              fontFamily="monospace"
            >
              MEDTRACE-ET · RX
            </text>
            <path d="M142 27 h5 v-5 h5 v5 h5 v5 h-5 v5 h-5 v-5 h-5 z" fill="#ffffff" />
            <text
              x="14"
              y="72"
              fill="#112421"
              fontSize="12"
              fontWeight="800"
              fontFamily="sans-serif"
            >
              AMOXICILLIN 500mg
            </text>
            <text x="14" y="87" fill="#49615c" fontSize="9" fontFamily="monospace">
              GTIN 09506000134352
            </text>
            <g transform="translate(14, 98)">
              <rect
                x="0"
                y="0"
                width="64"
                height="64"
                fill="#ffffff"
                stroke="#0b4f4a"
                strokeWidth="1.5"
              />
              <rect x="6" y="6" width="5" height="52" fill="#0f1e1c" />
              <rect x="6" y="53" width="52" height="5" fill="#0f1e1c" />
              <rect x="16" y="11" width="8" height="8" fill="#0f1e1c" />
              <rect x="30" y="11" width="8" height="8" fill="#0f1e1c" />
              <rect x="44" y="11" width="8" height="8" fill="#0f1e1c" />
              <rect x="22" y="23" width="14" height="8" fill="#0f1e1c" />
              <rect x="42" y="23" width="10" height="10" fill="#0f1e1c" />
              <rect x="16" y="35" width="10" height="12" fill="#0f1e1c" />
              <rect x="32" y="38" width="18" height="9" fill="#0f1e1c" />
            </g>
            <text x="86" y="114" fill="#49615c" fontSize="8" fontFamily="monospace">
              (21) SERIAL
            </text>
            <text
              x="86"
              y="127"
              fill="#0b4f4a"
              fontSize="10"
              fontWeight="700"
              fontFamily="monospace"
            >
              DEMO0001
            </text>
            <text x="86" y="145" fill="#49615c" fontSize="8" fontFamily="monospace">
              (10) BATCH42
            </text>
            <text x="86" y="158" fill="#49615c" fontSize="8" fontFamily="monospace">
              (17) 2030-12-31
            </text>
            <rect x="14" y="176" width="140" height="26" rx="6" fill="#dcfce7" stroke="#059669" />
            <path
              d="M23 189 l3.5 3.5 l6.5 -7"
              stroke="#065f46"
              strokeWidth="2.2"
              fill="none"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
            <text
              x="36"
              y="193"
              fill="#065f46"
              fontSize="10"
              fontWeight="800"
              fontFamily="sans-serif"
            >
              CHECKS PASSED
            </text>
          </g>
          <rect
            x="40"
            y="152"
            width="280"
            height="4"
            rx="2"
            fill="url(#heroLaserLine)"
            className="svg-laser-sweep"
          />
          <g stroke="#2dd4bf" strokeWidth="2.5" fill="none">
            <path d="M54 34 H38 V50" />
            <path d="M306 34 H322 V50" />
            <path d="M54 246 H38 V230" />
            <path d="M306 246 H322 V230" />
          </g>
        </svg>
      </div>
    </div>
  );
}

function HeroScannerShowcase() {
  const [SceneComp, setSceneComp] = useState<ComponentType<{ embedded?: boolean }> | null>(null);
  useEffect(() => {
    if (!shouldAutoLoadHeroThree()) return;
    let active = true;
    const timer = window.setTimeout(() => {
      import("./MedicineScene")
        .then((m) => {
          if (active) setSceneComp(() => m.default);
        })
        .catch(() => {});
    }, 60);
    return () => {
      active = false;
      clearTimeout(timer);
    };
  }, []);

  if (SceneComp) {
    return <SceneComp embedded />;
  }
  return <HeroStaticSvgFallback />;
}

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
      <div className="login-card-header">
        <span className="eyebrow">{t("workspace")}</span>
        <h2>{t("loginTitle")}</h2>
        <p className="muted">{t("loginHint")}</p>
      </div>
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
        {t(busy ? "signingIn" : "signIn")} <span aria-hidden="true">→</span>
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
          <img src="/logo.svg" alt="" width="34" height="34" />
          <span>{t("brand")}</span>
        </a>
        <div className="header-actions">
          <LanguageSwitch />
          <button
            className="theme-button"
            aria-label={t(theme === "light" ? "dark" : "light")}
            onClick={() => setTheme(theme === "light" ? "dark" : "light")}
          >
            <Icon name={theme === "light" ? "moon" : "sun"} size={19} />
          </button>
          {session && (
            <button className="signout" onClick={() => supabase.auth.signOut({ scope: "local" })}>
              {t("signOut")}
            </button>
          )}
        </div>
      </header>
      <div className="statusbar">
        <span className="statusbar-site mono">
          {session ? (site ?? t("inspector")) : t("tagline")}
        </span>
        <ServerStatus />
      </div>

      <div className={session ? "app-shell authenticated" : "app-shell"}>
        {session && (
          <nav aria-label={t("workspace")} className="workspace-nav">
            {(["scan", "history", "demo", "tools"] as Tab[]).map((item) => (
              <button
                key={item}
                aria-current={tab === item ? "page" : undefined}
                className={tab === item ? "active" : ""}
                onClick={() => setTab(item)}
              >
                <Icon name={item} />
                <span>{item === "history" && !site ? t("inspector") : t(item)}</span>
              </button>
            ))}
          </nav>
        )}

        <main id="main">
          <LoadBoundary key={tab}>
            <Suspense
              fallback={
                <div className="card skeleton-card" role="status">
                  <div className="skeleton-line wide" />
                  <div className="skeleton-line" />
                  <span>{t("loading")}</span>
                </div>
              }
            >
              {tab === "demo" ? (
                <DemoPage onClose={() => setTab("scan")} />
              ) : !session ? (
                <>
                  <div className="welcome-grid">
                    <section className="welcome">
                      <span className="eyebrow">{t("workspace")}</span>
                      <h1>{t("welcome")}</h1>
                      <p>{t("intro")}</p>
                      <HeroScannerShowcase />
                      <div className="welcome-cta-row">
                        <button className="secondary" onClick={() => setTab("demo")}>
                          {t("demo")} <Icon name="arrow" />
                        </button>
                      </div>
                    </section>
                    <Login />
                  </div>
                  <section className="quick-tools">
                    <button
                      className="tool-button"
                      onClick={() => setShowTools(!showTools)}
                      aria-expanded={showTools}
                    >
                      <span>{t("parseTitle")}</span>
                      <Icon name="arrow" />
                    </button>
                    <button
                      className="tool-button"
                      onClick={() => setShowThree(!showThree)}
                      aria-expanded={showThree}
                    >
                      <span>{t("loadThree")}</span>
                      <Icon name="cube" size={19} />
                    </button>
                  </section>
                  {showTools && <ParseTool />}
                  {showThree && <MedicineScene />}
                </>
              ) : tab === "scan" ? (
                <div className="tab-panel">
                  <div className="page-heading">
                    <span className="eyebrow mono">{site ?? t("inspector")}</span>
                    <h1>{t("scanTitle")}</h1>
                    <p>{t("scanIntro")}</p>
                  </div>
                  <ScanPage
                    onHistory={(gtin, serial) => {
                      setHistoryFor({ gtin, serial });
                      setTab("history");
                    }}
                  />
                </div>
              ) : tab === "history" ? (
                <div className="tab-panel">
                  <HistoryPage initial={historyFor} inspector={!site} />
                </div>
              ) : (
                <div className="tab-panel page">
                  <ParseTool />
                  <DemoCodes />
                  <button className="secondary" onClick={() => setShowThree(!showThree)}>
                    {t("loadThree")}
                  </button>
                  {showThree && <MedicineScene />}
                </div>
              )}
            </Suspense>
          </LoadBoundary>
          <footer>
            <span className="footer-brand">{t("brand")}</span>
            <p>{t("footer")}</p>
            <small>{t("offlineHint")}</small>
          </footer>
        </main>
      </div>
    </>
  );
}
