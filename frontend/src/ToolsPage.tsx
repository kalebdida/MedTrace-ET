import { useEffect, useRef, useState } from "react";
import { useI18n } from "./i18n";
import type { TranslationKey } from "./translations";
import { api, type Product } from "./api";
import { SAMPLES, fromVisible, freshSerial, pharmaBarcode, visible } from "./samples";

/** Public barcode checker (no sign-in): calls /parse. */
export function ParseTool() {
  const { t } = useI18n();
  const [busy, setBusy] = useState(false);
  const [barcode, setBarcode] = useState(SAMPLES[0].barcode());
  const [result, setResult] = useState<Product | null>(null);
  const [error, setError] = useState("");

  async function parse() {
    setError("");
    setBusy(true);
    setResult(null);
    try {
      setResult(
        await api<Product>("/parse", { method: "POST", body: JSON.stringify({ barcode }) }),
      );
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="card">
      <h3>{t("parseTitle")}</h3>
      <p>{t("parseHint")}</p>
      <textarea
        aria-label={t("barcode")}
        rows={2}
        value={visible(barcode)}
        onChange={(e) => setBarcode(fromVisible(e.target.value))}
      />
      <div className="chips">
        {SAMPLES.map((s) => (
          <button key={s.label} className="chip" onClick={() => setBarcode(s.barcode())}>
            {t(s.label)}
          </button>
        ))}
      </div>
      <button className="primary" onClick={parse} disabled={busy}>
        {t(busy ? "loading" : "parse")}
      </button>
      {error && <p className="error">{t(error as TranslationKey)}</p>}
      {result && (
        <div className={`result ${result.valid ? "pass" : "fail"}`}>
          <h3>{result.valid ? t("validCode") : t("invalidCode")}</h3>
          <dl>
            <dt>{t("gtin")}</dt>
            <dd>{result.gtin ?? "–"}</dd>
            <dt>{t("serial")}</dt>
            <dd>{result.serial ?? "–"}</dd>
            <dt>{t("batch")}</dt>
            <dd>{result.batch ?? "–"}</dd>
            <dt>{t("expiry")}</dt>
            <dd>{result.expiry ?? "–"}</dd>
          </dl>
          {[...result.errors, ...result.warnings].map((i) => (
            <p key={i.code} className="small">
              {i.message}
            </p>
          ))}
        </div>
      )}
    </section>
  );
}

/** Renders printable GS1 DataMatrix codes so the demo can be scanned with a phone. */
export function DemoCodes() {
  const { t } = useI18n();
  const [codeError, setCodeError] = useState(false);
  const [show, setShow] = useState(false);
  const [serial, setSerial] = useState(freshSerial);
  const canvas = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    if (!canvas.current || !show) return;
    let active = true;
    setCodeError(false);
    void import("bwip-js")
      .then(({ default: bwipjs }) => {
        if (!active || !canvas.current) return;
        // bwip-js takes the bracketed form and encodes proper FNC1 separators.
        bwipjs.toCanvas(canvas.current, {
          bcid: "gs1datamatrix",
          text: `(01)09506000134352(17)301231(10)BATCH42(21)${serial}`,
          scale: 5,
        });
      })
      .catch(() => {
        if (active) setCodeError(true);
      });
    return () => {
      active = false;
    };
  }, [serial, show]);

  return (
    <section className="card">
      <h3>{t("codes")}</h3>
      <p className="small">{t("codesHint")}</p>
      <button className="secondary" onClick={() => setShow(!show)} aria-expanded={show}>
        {t("printCode")}
      </button>
      {codeError && (
        <p className="error" role="alert">
          {t("networkError")}
        </p>
      )}
      {show && <canvas ref={canvas} className="dm" aria-label={t("codes")} role="img" />}
      <p className="mono small">{visible(pharmaBarcode(serial))}</p>
      <button className="secondary" onClick={() => setSerial(freshSerial())}>
        {t("newSerial")}
      </button>
    </section>
  );
}
