import { lazy, Suspense, useCallback, useEffect, useState } from "react";
import { api, currentToken, ApiError, type History, type Flag } from "./api";
import { Icon } from "./Icon";
import { useI18n } from "./i18n";
import type { TranslationKey } from "./translations";

const CloneMap = lazy(() => import("./CloneMap"));

export type AlertItem = {
  event_id?: string;
  pk?: string;
  identity?: string;
  gtin?: string | null;
  serial?: string | null;
  site_id?: string | null;
  prior_site_id?: string | null;
  scanned_at?: string;
  verdict?: string;
  distance_km?: number;
  speed_kmh?: number;
  flags?: Flag[];
  product?: { gtin?: string | null; serial?: string | null };
};

type AlertsEnvelope =
  | AlertItem[]
  | {
      alerts?: AlertItem[];
      items?: AlertItem[];
      events?: AlertItem[];
      next_before?: string | null;
      before?: string | null;
    };

function parsePackIdentity(item: AlertItem): { gtin: string; serial: string } {
  const gtin =
    item.gtin ??
    item.product?.gtin ??
    (item.pk?.startsWith("SGTIN#") ? item.pk.split("#")[1] : undefined) ??
    (item.identity?.startsWith("SGTIN#") ? item.identity.split("#")[1] : undefined) ??
    "09506000134352";
  const serial =
    item.serial ??
    item.product?.serial ??
    (item.pk?.startsWith("SGTIN#") ? item.pk.split("#")[2] : undefined) ??
    (item.identity?.startsWith("SGTIN#") ? item.identity.split("#")[2] : undefined) ??
    item.identity ??
    "DEMO0001";
  return { gtin, serial };
}

function normalizeAlerts(raw: AlertsEnvelope): { list: AlertItem[]; nextBefore: string | null } {
  if (Array.isArray(raw)) {
    const last = raw[raw.length - 1];
    return {
      list: raw,
      nextBefore: raw.length >= 10 && last?.scanned_at ? last.scanned_at : null,
    };
  }
  const list = raw?.alerts ?? raw?.items ?? raw?.events ?? [];
  const nextBefore = raw?.next_before ?? raw?.before ?? null;
  return { list, nextBefore };
}

export function HistoryView({ history, autoMap = false }: { history: History; autoMap?: boolean }) {
  const { t, language } = useI18n();
  const [showMap, setShowMap] = useState(autoMap);
  return (
    <div className="history-results">
      {history.scan_count === 0 ? (
        <div className="card empty-state-card">
          <p>{t("noRecords")}</p>
        </div>
      ) : (
        <>
          <div className={`chain-status ${history.chain.valid ? "pass" : "fail"}`} role="status">
            <span className="chain-seal-icon" aria-hidden="true">
              <Icon name={history.chain.valid ? "check" : "cross"} size={24} />
            </span>
            <div className="chain-status-body">
              <div className="chain-status-row">
                <strong>{t(history.chain.valid ? "intact" : "tampered")}</strong>
                <span className="chain-seal-badge mono">
                  <Icon name={history.chain.valid ? "check" : "cross"} size={13} />
                  <span>{history.chain.valid ? "SHA-256" : "TAMPERED"}</span>
                </span>
              </div>
              <small>
                {history.scan_count} {t("records")} ·{" "}
                {t(history.chain.valid ? "chainSealIntact" : "chainSealTampered")}
              </small>
            </div>
          </div>
          {history.truncated && <p className="hint">{t("truncated")}</p>}
          <section className="card map-card">
            <div className="map-card-header">
              <div>
                <h2>{t("map")}</h2>
                <p className="hint">{t("mapHint")}</p>
              </div>
              {!showMap && (
                <button className="secondary" onClick={() => setShowMap(true)}>
                  {t("loadMap")}
                </button>
              )}
            </div>
            {showMap && (
              <Suspense
                fallback={
                  <div className="skeleton-block" role="status">
                    {t("loading")}
                  </div>
                }
              >
                <CloneMap events={history.events} />
              </Suspense>
            )}
          </section>
          <ol className="timeline">
            {history.events.map((e) => (
              <li key={e.seq} className={`timeline-item ${e.verdict.toLowerCase()}`}>
                <span className="timeline-number">{e.seq}</span>
                <div className="timeline-content">
                  <div className="timeline-title">
                    <strong className="mono">{e.site_id ?? t("unknownSite")}</strong>
                    <span className={`verdict-pill ${e.verdict.toLowerCase()}`}>
                      <Icon
                        name={
                          e.verdict === "PASS" ? "check" : e.verdict === "WARN" ? "warn" : "cross"
                        }
                        size={13}
                      />
                      <span>{e.verdict}</span>
                    </span>
                  </div>
                  <p className="timeline-meta">
                    {new Date(e.scanned_at).toLocaleString(language === "am" ? "am-ET" : "en-GB")} ·{" "}
                    <span className="mono">{e.event_type}</span>
                  </p>
                  <p className="mono small timeline-coords">
                    {e.location
                      ? `${e.location.lat.toFixed(4)}, ${e.location.lon.toFixed(4)}`
                      : t("noCoordinates")}
                  </p>
                  <p className="mono small timeline-hash">
                    #{e.seq} · {(e.record_hash ?? "0123456789abcdef").slice(0, 16)}…
                  </p>
                  {(e.flags ?? [])
                    .filter((f) => f.clone_indicator)
                    .map((f) => (
                      <details key={f.code} className="timeline-flag-details">
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
  const { t, language } = useI18n();
  const [gtin, setGtin] = useState(initial?.gtin ?? "");
  const [serial, setSerial] = useState(initial?.serial ?? "");
  const [history, setHistory] = useState<History | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  // Inspector Alerts Dashboard State
  const [alerts, setAlerts] = useState<AlertItem[]>([]);
  const [nextBefore, setNextBefore] = useState<string | null>(null);
  const [alertsBusy, setAlertsBusy] = useState(false);
  const [alertsStatus, setAlertsStatus] = useState<"idle" | "ok" | "403" | "501" | "error">("idle");

  const loadAlerts = useCallback(async (beforeCursor?: string | null) => {
    setAlertsBusy(true);
    if (!beforeCursor) setAlertsStatus("idle");
    try {
      const token = await currentToken();
      const q = beforeCursor ? `?before=${encodeURIComponent(beforeCursor)}` : "";
      const raw = await api<AlertsEnvelope>(`/alerts${q}`, {}, token);
      const { list, nextBefore: next } = normalizeAlerts(raw);
      setAlerts((prev) => (beforeCursor ? [...prev, ...list] : list));
      setNextBefore(next);
      setAlertsStatus("ok");
    } catch (e) {
      if (e instanceof ApiError && e.status === 403) {
        setAlertsStatus("403");
      } else if (e instanceof ApiError && e.status === 501) {
        setAlertsStatus("501");
      } else {
        setAlertsStatus("error");
      }
    } finally {
      setAlertsBusy(false);
    }
  }, []);

  useEffect(() => {
    if (inspector) {
      void loadAlerts();
    }
  }, [inspector, loadAlerts]);

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

      {/* Inspector Recent Clone Alerts Dashboard */}
      {inspector && (
        <section className="card alerts-dashboard" data-testid="alerts-dashboard">
          <div className="alerts-header">
            <div>
              <span className="eyebrow">{t("inspector")}</span>
              <h2>{t("alertsTitle")}</h2>
              <p className="hint">{t("alertsSubtitle")}</p>
            </div>
            <button
              type="button"
              className="secondary compact-btn"
              onClick={() => void loadAlerts()}
              disabled={alertsBusy}
            >
              {t("refreshAlerts")}
            </button>
          </div>

          {alertsBusy && alerts.length === 0 && (
            <div className="skeleton-list" role="status">
              <div className="skeleton-line" />
              <div className="skeleton-line" />
              <span>{t("alertsLoading")}</span>
            </div>
          )}

          {alertsStatus === "403" && (
            <div className="alerts-status-banner warn" role="status">
              <span className="status-badge-code mono">403</span>
              <p>{t("alertsForbidden")}</p>
            </div>
          )}

          {alertsStatus === "501" && (
            <div className="alerts-status-banner info" role="status">
              <span className="status-badge-code mono">501</span>
              <p>{t("alertsUnavailable501")}</p>
            </div>
          )}

          {alertsStatus === "error" && (
            <div className="alerts-status-banner info" role="status">
              <p>{t("alertsError")}</p>
            </div>
          )}

          {alertsStatus === "ok" && alerts.length === 0 && !alertsBusy && (
            <p className="hint">{t("alertsEmpty")}</p>
          )}

          {alerts.length > 0 && (
            <ul className="alerts-list">
              {alerts.map((item, idx) => {
                const { gtin: itemGtin, serial: itemSerial } = parsePackIdentity(item);
                const travelFlag =
                  item.flags?.find((f) => f.code === "IMPOSSIBLE_TRAVEL") ?? item.flags?.[0];
                const flagMsg = travelFlag?.message ?? "";
                const siteMatch = flagMsg.match(/site\s+([A-Z0-9-]+)/i);
                const kmMatch = flagMsg.match(/(\d+(?:\.\d+)?)\s*km\b/i);
                const priorSite =
                  item.prior_site_id ??
                  (typeof travelFlag?.details?.prior_site_id === "string"
                    ? travelFlag.details.prior_site_id
                    : siteMatch?.[1]);
                const distKm =
                  item.distance_km ??
                  (typeof travelFlag?.details?.distance_km === "number"
                    ? Math.round(travelFlag.details.distance_km)
                    : kmMatch
                      ? Math.round(Number(kmMatch[1]))
                      : undefined);
                const speedKmh =
                  item.speed_kmh ??
                  (typeof travelFlag?.details?.speed_kmh === "number"
                    ? Math.round(travelFlag.details.speed_kmh)
                    : undefined);

                return (
                  <li
                    key={item.event_id ?? `${itemGtin}-${itemSerial}-${idx}`}
                    className="alert-row"
                  >
                    <div className="alert-row-main">
                      <div className="alert-row-top">
                        <span className="verdict-pill fail">
                          <Icon name="cross" size={13} />
                          <span>{item.verdict ?? "FAIL"} · CLONE</span>
                        </span>
                        <strong className="mono">
                          {itemGtin} · {itemSerial}
                        </strong>
                      </div>
                      <p className="alert-row-route">
                        {priorSite ? `${priorSite} → ` : ""}
                        <strong>{item.site_id ?? t("unknownSite")}</strong>
                        {distKm ? ` · ${distKm} km` : ""}
                        {speedKmh ? ` (${speedKmh} km/h)` : ""}
                      </p>
                      {flagMsg && <p className="hint">{flagMsg}</p>}
                      {item.scanned_at && (
                        <small className="mono">
                          {new Date(item.scanned_at).toLocaleString(
                            language === "am" ? "am-ET" : "en-GB",
                          )}
                        </small>
                      )}
                    </div>
                    <button
                      type="button"
                      className="secondary alert-inspect-btn"
                      onClick={() => {
                        setGtin(itemGtin);
                        setSerial(itemSerial);
                        void load(itemGtin, itemSerial);
                      }}
                    >
                      {t("inspectAlertPack")} →
                    </button>
                  </li>
                );
              })}
            </ul>
          )}

          {nextBefore && (
            <button
              type="button"
              className="secondary"
              disabled={alertsBusy}
              onClick={() => void loadAlerts(nextBefore)}
            >
              {t(alertsBusy ? "loading" : "loadOlderAlerts")}
            </button>
          )}
        </section>
      )}

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
            placeholder="09506000134352"
            required
          />
        </label>
        <label>
          {t("serial")}
          <input
            value={serial}
            onChange={(e) => setSerial(e.target.value)}
            placeholder="DEMO0001"
            required
          />
        </label>
        <button className="primary" disabled={busy || !gtin.trim() || !serial.trim()}>
          {t(busy ? "loading" : "showHistory")} <span aria-hidden="true">→</span>
        </button>
      </form>
      {busy && (
        <div className="card skeleton-card" role="status">
          <div className="skeleton-line wide" />
          <div className="skeleton-line" />
          <span>{t("loading")}</span>
        </div>
      )}
      {error && (
        <p className="error" role="alert">
          {t(error as TranslationKey)}
        </p>
      )}
      {history && <HistoryView history={history} autoMap={inspector} />}
    </section>
  );
}
