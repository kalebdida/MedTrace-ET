import { useCallback, useState } from "react";
import { api, currentToken, type ScanResult } from "./api";
import { ResultCard } from "./ResultCard";
import { Scanner } from "./Scanner";
import { SAMPLES, freshSerial, fromVisible, pharmaBarcode, visible } from "./samples";

type Location = { lat: number; lon: number; accuracy_m: number };

// Demo only: lets one person show scans in two cities. Clearly labelled in the UI.
const DEMO_PLACES: Record<string, Location> = {
  "Addis Ababa": { lat: 9.0108, lon: 38.7613, accuracy_m: 20 },
  Adama: { lat: 8.54, lon: 39.27, accuracy_m: 20 },
  Dessie: { lat: 11.13, lon: 39.6333, accuracy_m: 20 },
};

function getLocation(): Promise<Location | null> {
  return new Promise((resolve) => {
    if (!navigator.geolocation) return resolve(null);
    navigator.geolocation.getCurrentPosition(
      (p) => resolve({ lat: p.coords.latitude, lon: p.coords.longitude, accuracy_m: p.coords.accuracy }),
      () => resolve(null),
      { enableHighAccuracy: true, timeout: 10000 },
    );
  });
}

/** Downscales a phone photo to a JPEG under the backend's 1.5 MB limit; returns base64. */
async function photoToBase64(file: File): Promise<string> {
  const bitmap = await createImageBitmap(file);
  const scale = Math.min(1, 1280 / Math.max(bitmap.width, bitmap.height));
  const canvas = document.createElement("canvas");
  canvas.width = Math.round(bitmap.width * scale);
  canvas.height = Math.round(bitmap.height * scale);
  canvas.getContext("2d")!.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
  return canvas.toDataURL("image/jpeg", 0.85).split(",")[1];
}

export function ScanPage({ onHistory }: { onHistory: (gtin: string, serial: string) => void }) {
  const [barcode, setBarcode] = useState("");
  const [eventType, setEventType] = useState("verify");
  const [place, setPlace] = useState("gps");
  const [photo, setPhoto] = useState<File | null>(null);
  const [scanning, setScanning] = useState(false);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [result, setResult] = useState<ScanResult | null>(null);

  const onScan = useCallback((text: string) => {
    setScanning(false);
    setBarcode(text);
  }, []);

  async function submit() {
    setError("");
    setResult(null);
    setBusy("Getting location…");
    const location = place === "gps" ? await getLocation() : DEMO_PLACES[place];
    const body: Record<string, unknown> = {
      barcode: fromVisible(barcode.trim()),
      event_type: eventType,
      scanned_at: new Date().toISOString(),
    };
    if (location) body.location = location;
    if (photo) body.package_image = await photoToBase64(photo);
    setBusy("Verifying… (the first request can take up to a minute while the server wakes up)");
    try {
      setResult(await api<ScanResult>("/scan", { method: "POST", body: JSON.stringify(body) }, await currentToken()));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy("");
    }
  }

  return (
    <div className="page">
      {scanning ? (
        <Scanner onScan={onScan} onClose={() => setScanning(false)} />
      ) : (
        <button className="primary big" onClick={() => setScanning(true)}>📷 Scan DataMatrix</button>
      )}

      <label>
        Barcode (scanned, typed or pasted)
        <textarea value={visible(barcode)} onChange={(e) => setBarcode(fromVisible(e.target.value))} rows={2} />
      </label>
      <div className="chips">
        {SAMPLES.map((s) => (
          <button key={s.label} className="chip" onClick={() => setBarcode(s.barcode())}>{s.label}</button>
        ))}
        <button className="chip" onClick={() => setBarcode(pharmaBarcode(freshSerial()))}>New demo serial</button>
      </div>

      <label>
        What are you doing?
        <select value={eventType} onChange={(e) => setEventType(e.target.value)}>
          <option value="verify">Verify (check a pack)</option>
          <option value="receive">Receive a delivery</option>
          <option value="dispense">Dispense to a patient</option>
          <option value="ship">Ship onward</option>
        </select>
      </label>

      <label>
        Location
        <select value={place} onChange={(e) => setPlace(e.target.value)}>
          <option value="gps">My phone's GPS</option>
          {Object.keys(DEMO_PLACES).map((p) => <option key={p} value={p}>Demo: pretend I'm in {p}</option>)}
        </select>
      </label>

      <label>
        Package photo (optional, enables the packaging check)
        <input type="file" accept="image/*" capture="environment" onChange={(e) => setPhoto(e.target.files?.[0] ?? null)} />
      </label>

      <button className="primary big" disabled={!barcode.trim() || !!busy} onClick={submit}>Verify pack</button>
      {busy && <p className="hint">{busy}</p>}
      {error && <p className="error">{error}</p>}
      {result && (
        <ResultCard
          result={result}
          onHistory={() => onHistory(result.product.gtin!, result.product.serial!)}
        />
      )}
    </div>
  );
}
