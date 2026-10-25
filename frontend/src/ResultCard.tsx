import type { ScanResult } from "./api";

const TITLES = {
  PASS: "Genuine: safe to dispense",
  WARN: "Check before dispensing",
  FAIL: "Do NOT dispense",
};

export function ResultCard({ result, onHistory }: { result: ScanResult; onHistory?: () => void }) {
  const p = result.product;
  return (
    <section className={`result ${result.verdict.toLowerCase()}`} data-testid="result">
      <h2>
        {result.verdict === "PASS" ? "✓" : result.verdict === "WARN" ? "!" : "✗"} {TITLES[result.verdict]}
      </h2>
      {result.clone_suspected && (
        <p className="banner">
          Cloned barcode intercepted{result.alert_sent ? "; EFDA alert sent" : ""}
        </p>
      )}
      {result.flags.length > 0 && (
        <ul className="flags">
          {result.flags.map((f) => (
            <li key={f.code} className={f.severity}>
              <strong>{f.code.replace(/_/g, " ")}</strong>
              <span>{f.message}</span>
            </li>
          ))}
        </ul>
      )}
      <dl>
        <dt>GTIN</dt><dd>{p.gtin ?? "–"}</dd>
        <dt>Serial</dt><dd>{p.serial ?? "–"}</dd>
        <dt>Batch</dt><dd>{p.batch ?? "–"}</dd>
        <dt>Expiry</dt><dd>{p.expiry ?? "–"}</dd>
        <dt>Site</dt><dd>{result.site_id ?? "–"}</dd>
        {result.visual && (
          <>
            <dt>Packaging</dt>
            <dd>
              {result.visual.status}
              {result.visual.similarity != null && ` (${Math.round(result.visual.similarity * 100)}% match)`}
            </dd>
          </>
        )}
        <dt>Audit record</dt>
        <dd className="mono">#{result.audit.seq} · {result.audit.record_hash.slice(0, 16)}…</dd>
      </dl>
      {onHistory && p.gtin && p.serial && (
        <button className="secondary" onClick={onHistory}>View this pack's history</button>
      )}
    </section>
  );
}
