import type { ScanResult } from "./api";
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
export function ResultCard({ result, onHistory }: { result: ScanResult; onHistory?: () => void }) {
  const { t } = useI18n();
  const p = result.product;
  return (
    <section
      className={`result ${result.verdict.toLowerCase()}`}
      data-testid="result"
      aria-label={t("result")}
    >
      <div className="result-heading">
        <span className="verdict-icon" aria-hidden>
          {result.verdict === "PASS" ? "✓" : result.verdict === "WARN" ? "!" : "×"}
        </span>
        <div>
          <span className="eyebrow">{result.verdict}</span>
          <h2>{t(result.verdict)}</h2>
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
      {result.clone_suspected && (
        <div className="banner">
          <strong>{t("clone")}</strong>
          <span>{t(result.alert_sent ? "alertSent" : "alertNotSent")}</span>
        </div>
      )}
      {result.flags.length > 0 && (
        <ul className="flags">
          {result.flags.map((f) => (
            <li key={f.code} className={f.severity}>
              <strong>{t(flags[f.code] ?? "flagOther")}</strong>
              <details>
                <summary>{t("technical")}</summary>
                <code>{f.code}</code>
                <p>{f.message}</p>
              </details>
            </li>
          ))}
        </ul>
      )}
      <dl>
        {(
          [
            ["gtin", p.gtin],
            ["serial", p.serial],
            ["batch", p.batch],
            ["expiry", p.expiry],
            ["site", result.site_id],
          ] as const
        ).map(([key, value]) => (
          <div key={key}>
            <dt>{t(key)}</dt>
            <dd>{value ?? "—"}</dd>
          </div>
        ))}
        <div>
          <dt>{t("packaging")}</dt>
          <dd>{t(result.visual ? (visual[result.visual.status] ?? "modelError") : "noPhoto")}</dd>
        </div>
        <div>
          <dt>{t("audit")}</dt>
          <dd className="mono">
            #{result.audit.seq} · {result.audit.record_hash.slice(0, 16)}…
          </dd>
        </div>
      </dl>
      {onHistory && p.gtin && p.serial && (
        <button className="secondary" onClick={onHistory}>
          {t("viewHistory")} →
        </button>
      )}
    </section>
  );
}
