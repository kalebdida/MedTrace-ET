import { lazy, Suspense, useEffect, useState } from "react";
import { api, currentToken, ApiError, type History } from "./api";
import { useI18n } from "./i18n";
import type { TranslationKey } from "./translations";
const CloneMap = lazy(() => import("./CloneMap"));
export function HistoryView({ history, autoMap = false }: { history: History; autoMap?: boolean }) {
  const { t, language } = useI18n();
  const [showMap, setShowMap] = useState(autoMap);
  return (
    <div className="history-results">
      {history.scan_count === 0 ? (
        <p>{t("noRecords")}</p>
      ) : (
        <>
          <div className={`chain-status ${history.chain.valid ? "pass" : "fail"}`} role="status">
            <span aria-hidden>{history.chain.valid ? "✓" : "!"}</span>
            <div>
              <strong>{t(history.chain.valid ? "intact" : "tampered")}</strong>
              <small>
                {history.scan_count} {t("records")}
              </small>
            </div>
          </div>
          {history.truncated && <p>{t("truncated")}</p>}
          <section className="card">
            <h2>{t("map")}</h2>
            <p className="hint">{t("mapHint")}</p>
            {showMap ? (
              <Suspense fallback={<p>{t("loading")}</p>}>
                <CloneMap events={history.events} />
              </Suspense>
            ) : (
              <button className="secondary" onClick={() => setShowMap(true)}>
                {t("loadMap")}
              </button>
            )}
          </section>
          <ol className="timeline">
            {history.events.map((e) => (
              <li key={e.seq} className={e.verdict.toLowerCase()}>
                <span className="timeline-number">{e.seq}</span>
                <div>
                  <div className="timeline-title">
                    <strong>{e.site_id ?? t("unknownSite")}</strong>
                    <span className="verdict-pill">{e.verdict}</span>
                  </div>
                  <p>
                    {new Date(e.scanned_at).toLocaleString(language === "am" ? "am-ET" : "en-GB")} ·{" "}
                    {e.event_type}
                  </p>
                  <p className="mono small">
                    {e.location
                      ? `${e.location.lat.toFixed(4)}, ${e.location.lon.toFixed(4)}`
                      : t("noCoordinates")}
                  </p>
                  {(e.flags ?? [])
                    .filter((f) => f.clone_indicator)
                    .map((f) => (
                      <details key={f.code}>
                        <summary>{t("technical")}</summary>
                        <p>{f.message}</p>
                      </details>
                    ))}
                </div>
              </li>
            ))}
          </ol>
        </>
      )}
    </div>
  );
}
export function HistoryPage({
  initial,
  inspector = false,
}: {
  initial?: { gtin: string; serial: string };
  inspector?: boolean;
}) {
  const { t } = useI18n();
  const [gtin, setGtin] = useState(initial?.gtin ?? "");
  const [serial, setSerial] = useState(initial?.serial ?? "");
  const [history, setHistory] = useState<History | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  async function load(g = gtin, s = serial) {
    setError("");
    setBusy(true);
    setHistory(null);
    try {
      const q = new URLSearchParams({ gtin: g.trim(), serial: s.trim() });
      setHistory(await api<History>(`/history?${q}`, {}, await currentToken()));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "requestFailed");
    } finally {
      setBusy(false);
    }
  }
  useEffect(() => {
    if (initial) void load(initial.gtin, initial.serial);
  }, [initial]);
  return (
    <section className="page">
      <div className="page-heading">
        <span className="eyebrow">{t(inspector ? "inspector" : "history")}</span>
        <h1>{t(inspector ? "inspectorTitle" : "historyTitle")}</h1>
        <p>{t(inspector ? "inspectorHint" : "historyIntro")}</p>
      </div>
      <form
        className="card lookup"
        onSubmit={(e) => {
          e.preventDefault();
          void load();
        }}
      >
        <label>
          {t("gtin")}
          <input
            value={gtin}
            onChange={(e) => setGtin(e.target.value)}
            inputMode="numeric"
            required
          />
        </label>
        <label>
          {t("serial")}
          <input value={serial} onChange={(e) => setSerial(e.target.value)} required />
        </label>
        <button className="primary" disabled={busy || !gtin.trim() || !serial.trim()}>
          {t(busy ? "loading" : "showHistory")} →
        </button>
      </form>
      {error && (
        <p className="error" role="alert">
          {t(error as TranslationKey)}
        </p>
      )}
      {history && <HistoryView history={history} />}
    </section>
  );
}
