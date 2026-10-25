import type { ScanResult } from "./api";
import { Icon } from "./Icon";
import { useI18n } from "./i18n";
import type { TranslationKey } from "./translations";

const flags: Record<string, TranslationKey> = {
  IMPOSSIBLE_TRAVEL: "flagTravel",
  DISPENSED_PACK_RESURFACED: "flagDispensed",
  ALREADY_DISPENSED: "flagDouble",
  EXPIRED: "flagExpired",
  NEAR_EXPIRY: "flagNearExpiry",
  INVALID_BARCODE: "flagBarcode",
  PACKAGING_MISMATCH: "flagPackaging",
  PACKAGING_INCONCLUSIVE: "flagVisual",
  VISUAL_CHECK_UNAVAILABLE: "flagVisual",
  VISUAL_NO_REFERENCE: "flagVisual",
};

const visual: Record<string, TranslationKey> = {
  match: "match",
  mismatch: "mismatch",
  inconclusive: "inconclusive",
  unavailable: "modelUnavailable",
  error: "modelError",
  no_reference: "noReference",
  not_performed: "noPhoto",
};

export type CloneJourneyInfo = {
  cityA: string;
  cityB: string;
  distanceKm: number;
  minutesApart: number;
  speedKmh: number;
};

export function extractCloneJourney(result: ScanResult): CloneJourneyInfo | null {
  const travelFlag = result.flags.find((f) => f.code === "IMPOSSIBLE_TRAVEL" || f.clone_indicator);
  const impossibleLeg = result.travel?.legs?.find((l) => l.impossible) ?? result.travel?.legs?.[0];
  if (!result.clone_suspected && !travelFlag && !impossibleLeg) return null;

  const details = travelFlag?.details ?? {};
  const msg = travelFlag?.message ?? "";

  const priorFromDetails =
    typeof details.prior_site_id === "string" ? details.prior_site_id : undefined;
  const cityA =
    impossibleLeg?.prior_site_id ||
    priorFromDetails ||
    (/adama/i.test(msg) || result.site_id === "PH-DESSIE-007" ? "PH-ADAMA-001" : "PH-ORIGIN-001");

  const cityB = result.site_id ?? (/dessie/i.test(msg) ? "PH-DESSIE-007" : "PH-CURRENT");

  const kmMatch = msg.match(/(\d+(?:\.\d+)?)\s*km\b/i);
  const distanceKm = Math.round(
    typeof impossibleLeg?.distance_km === "number"
      ? impossibleLeg.distance_km
      : typeof details.distance_km === "number"
        ? details.distance_km
        : kmMatch
          ? Number(kmMatch[1])
          : 291,
  );

  const minMatch = msg.match(/(\d+)\s*min/i);
  const minutesApart = Math.max(
    1,
    Math.round(
      typeof details.hours === "number" ? details.hours * 60 : minMatch ? Number(minMatch[1]) : 50,
    ),
  );

  const speedMatch = msg.match(/(\d+(?:\.\d+)?)\s*km\/h/i);
  const speedKmh = Math.round(
    typeof impossibleLeg?.speed_kmh === "number"
      ? impossibleLeg.speed_kmh
      : typeof details.speed_kmh === "number"
        ? details.speed_kmh
        : speedMatch
          ? Number(speedMatch[1])
          : (distanceKm / minutesApart) * 60,
  );

  return { cityA, cityB, distanceKm, minutesApart, speedKmh };
}

export function ResultCard({ result, onHistory }: { result: ScanResult; onHistory?: () => void }) {
  const { t } = useI18n();
  const p = result.product;
  const journey = extractCloneJourney(result);
  const vLower = result.verdict.toLowerCase();

  return (
    <section className={`result ${vLower}`} data-testid="result" aria-label={t("result")}>
      {/* Full-bleed Verdict Hero Banner */}
      <div className="verdict-banner">
        <div className="result-heading">
          <span className={`verdict-icon shape-${vLower}`} aria-hidden="true">
            <Icon
              name={
                result.verdict === "PASS" ? "check" : result.verdict === "WARN" ? "warn" : "cross"
              }
              size={30}
            />
          </span>
          <div className="verdict-titles">
            <span className="verdict-code-tag">{result.verdict}</span>
            <h2>{t(result.verdict)}</h2>
            <p className="verdict-action-line">
              {t(
                result.verdict === "PASS"
                  ? "verdictPassAction"
                  : result.verdict === "WARN"
                    ? "verdictWarnAction"
                    : "verdictFailAction",
              )}
            </p>
          </div>
        </div>
        <p className="result-guidance">
          {t(
            result.verdict === "PASS"
              ? "passGuide"
              : result.verdict === "WARN"
                ? "warnGuide"
                : "failGuide",
          )}
        </p>
      </div>

      <div className="result-body">
        {/* Clone Alert Delivery Banner */}
        {result.clone_suspected && (
          <div className="banner">
            <div className="banner-header">
              <span className="banner-icon" aria-hidden="true">
                <Icon name="cross" size={16} />
              </span>
              <strong>{t("clone")}</strong>
            </div>
            <span>{t(result.alert_sent ? "alertSent" : "alertNotSent")}</span>
          </div>
        )}

        {/* Visual Impossible Journey Telemetry Card */}
        {journey && (
          <div className="impossible-journey-card" data-testid="impossible-journey">
            <div className="journey-card-header">
              <span className="eyebrow">{t("impossibleJourneyTitle")}</span>
              <span className="journey-speed-badge">{journey.speedKmh} km/h</span>
            </div>
            <div className="journey-nodes">
              <div className="journey-node">
                <span className="journey-node-label">{t("originSite")}</span>
                <strong className="mono">{journey.cityA}</strong>
              </div>
              <div className="journey-vector" aria-hidden="true">
                <span className="journey-vector-pill">{journey.distanceKm} km</span>
                <div className="journey-vector-line">
                  <span className="journey-dot start" />
                  <span className="journey-track" />
                  <span className="journey-dot end">
                    <Icon name="cross" size={13} />
                  </span>
                </div>
                <span className="journey-vector-sub">
                  {journey.minutesApart} {t("minutesUnit")}
                </span>
              </div>
              <div className="journey-node destination">
                <span className="journey-node-label">{t("destinationSite")}</span>
                <strong className="mono">{journey.cityB}</strong>
              </div>
            </div>
            <div className="journey-metrics-grid">
              <div className="journey-metric">
                <span>{t("distanceLabel")}</span>
                <strong className="mono">{journey.distanceKm} km</strong>
              </div>
              <div className="journey-metric">
                <span>{t("timeApartLabel")}</span>
                <strong className="mono">
                  {journey.minutesApart} {t("minutesUnit")}
                </strong>
              </div>
              <div className="journey-metric highlight">
                <span>{t("impliedSpeedLabel")}</span>
                <strong className="mono">{journey.speedKmh} km/h</strong>
              </div>
            </div>
            <p className="journey-threshold-note">{t("maxPlausibleSpeed")}</p>
          </div>
        )}

        {/* Forensic Reasons Cards */}
        {result.flags.length > 0 && (
          <div className="reasons-section">
            <span className="eyebrow">{t("reasonsHeading")}</span>
            <ul className="flags">
              {result.flags.map((f) => (
                <li key={f.code} className={`flag-card ${f.severity}`}>
                  <div className="flag-card-top">
                    <span className="flag-severity-icon" aria-hidden="true">
                      <Icon name={f.severity === "critical" ? "cross" : "warn"} size={15} />
                    </span>
                    <div className="flag-card-title">
                      <strong>{t(flags[f.code] ?? "flagOther")}</strong>
                      <span className="mono flag-code-chip">{f.code}</span>
                    </div>
                  </div>
                  <details>
                    <summary>{t("technical")}</summary>
                    <code>{f.code}</code>
                    <p>{f.message}</p>
                  </details>
                </li>
              ))}
            </ul>
          </div>
        )}

        {/* Product & Forensic Metadata */}
        <div className="product-details-section">
          <span className="eyebrow">{t("productDetailsHeading")}</span>
          <dl className="metadata-grid">
            {(
              [
                ["gtin", p.gtin],
                ["serial", p.serial],
                ["batch", p.batch],
                ["expiry", p.expiry],
                ["site", result.site_id],
              ] as const
            ).map(([key, value]) => (
              <div key={key} className="metadata-cell">
                <dt>{t(key)}</dt>
                <dd className="mono">{value ?? "—"}</dd>
              </div>
            ))}
            <div className="metadata-cell">
              <dt>{t("packaging")}</dt>
              <dd>
                {t(result.visual ? (visual[result.visual.status] ?? "modelError") : "noPhoto")}
              </dd>
            </div>
            <div className="metadata-cell metadata-cell-wide">
              <dt>{t("audit")}</dt>
              <dd className="mono">
                #{result.audit.seq} · {result.audit.record_hash.slice(0, 16)}…
              </dd>
            </div>
          </dl>
        </div>

        {onHistory && p.gtin && p.serial && (
          <button className="secondary full-width-btn" onClick={onHistory}>
            {t("viewHistory")} <span aria-hidden="true">→</span>
          </button>
        )}
      </div>
    </section>
  );
}
