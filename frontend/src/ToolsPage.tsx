import { useEffect, useRef, useState } from "react";
import bwipjs from "bwip-js";
import { api, type Product } from "./api";
import { SAMPLES, fromVisible, freshSerial, pharmaBarcode, visible } from "./samples";

/** Public barcode checker (no sign-in): calls /parse. */
export function ParseTool() {
  const [barcode, setBarcode] = useState(SAMPLES[0].barcode());
  const [result, setResult] = useState<Product | null>(null);
  const [error, setError] = useState("");

  async function parse() {
    setError("");
    try {
      setResult(await api<Product>("/parse", { method: "POST", body: JSON.stringify({ barcode }) }));
    } catch (e) {
      setError((e as Error).message);
    }
  }

  return (
    <section className="card">
      <h3>Check a barcode (no sign-in)</h3>
      <textarea rows={2} value={visible(barcode)} onChange={(e) => setBarcode(fromVisible(e.target.value))} />
      <div className="chips">
        {SAMPLES.map((s) => <button key={s.label} className="chip" onClick={() => setBarcode(s.barcode())}>{s.label}</button>)}
      </div>
      <button className="primary" onClick={parse}>Parse</button>
      {error && <p className="error">{error}</p>}
      {result && (
        <div className={`result ${result.valid ? "pass" : "fail"}`}>
          <h3>{result.valid ? "✓ Valid GS1 code" : "✗ Invalid GS1 code"}</h3>
          <dl>
            <dt>GTIN</dt><dd>{result.gtin ?? "–"}</dd>
            <dt>Serial</dt><dd>{result.serial ?? "–"}</dd>
            <dt>Batch</dt><dd>{result.batch ?? "–"}</dd>
            <dt>Expiry</dt><dd>{result.expiry ?? "–"}</dd>
          </dl>
          {[...result.errors, ...result.warnings].map((i) => <p key={i.code} className="small">{i.message}</p>)}
        </div>
      )}
    </section>
  );
}

/** Renders printable GS1 DataMatrix codes so the demo can be scanned with a phone. */
export function DemoCodes() {
  const [serial, setSerial] = useState(freshSerial);
  const canvas = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    if (!canvas.current) return;
    // bwip-js takes the bracketed form and encodes proper FNC1 separators.
    bwipjs.toCanvas(canvas.current, {
      bcid: "gs1datamatrix",
      text: `(01)09506000134352(17)301231(10)BATCH42(21)${serial}`,
      scale: 5,
    });
  }, [serial]);

  return (
    <section className="card">
      <h3>Demo DataMatrix</h3>
      <p className="small">
        Show this on one screen and scan it with another phone, or print it. Scan the same code from two
        accounts in different cities to see a clone being caught.
      </p>
      <canvas ref={canvas} className="dm" />
      <p className="mono small">{visible(pharmaBarcode(serial))}</p>
      <button className="secondary" onClick={() => setSerial(freshSerial())}>New serial</button>
    </section>
  );
}
