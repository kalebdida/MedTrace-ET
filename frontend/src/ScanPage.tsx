import { lazy, Suspense, useCallback, useState } from "react";
import { api, currentToken, type ScanResult } from "./api";
import { ResultCard } from "./ResultCard";
import { useI18n } from "./i18n";
import { ApiError } from "./api";
import type { TranslationKey } from "./translations";
const Scanner = lazy(() => import("./Scanner").then((m) => ({ default: m.Scanner })));
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
      (p) =>
        resolve({ lat: p.coords.latitude, lon: p.coords.longitude, accuracy_m: p.coords.accuracy }),
      () => resolve(null),
      { enableHighAccuracy: true, timeout: 10000 },
    );
  });
}

/** Downscales a phone photo to a JPEG under the backend's 1.5 MB limit; returns base64. */
async function photoToBase64(file: File): Promise<string> {
  const bitmap = await createImageBitmap(file);
  const scale = Math.min(1, 960 / Math.max(bitmap.width, bitmap.height));
  const canvas = document.createElement("canvas");
  canvas.width = Math.round(bitmap.width * scale);
  canvas.height = Math.round(bitmap.height * scale);
  canvas.getContext("2d")!.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
  bitmap.close();
  for (const quality of [0.75, 0.6, 0.45, 0.3]) {
    const data = canvas.toDataURL("image/jpeg", quality).split(",")[1];
    if ((data.length * 3) / 4 <= 80000) return data;
  }
  const reduced = document.createElement("canvas");
  reduced.width = Math.max(1, Math.round(canvas.width / 2));
  reduced.height = Math.max(1, Math.round(canvas.height / 2));
  reduced.getContext("2d")!.drawImage(canvas, 0, 0, reduced.width, reduced.height);
  return reduced.toDataURL("image/jpeg", 0.5).split(",")[1];
}

export function ScanPage({ onHistory }: { onHistory: (gtin: string, serial: string) => void }) {
  const { t } = useI18n();
  const [notice, setNotice] = useState(false);
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
    setNotice(false);
    setBusy(t("locating"));
    const scannedAt = new Date().toISOString();
    try {
      const location = place === "gps" ? await getLocation() : DEMO_PLACES[place];
      setNotice(!location);
      const body: Record<string, unknown> = {
        barcode: fromVisible(barcode.trim()),
        event_type: eventType,
        scanned_at: scannedAt,
      };
      if (location) body.location = location;
      if (photo) {
        try {
          body.package_image = await photoToBase64(photo);
        } catch {
          throw new Error("photoFailed");
        }
      }
      setBusy(t("verifying"));
      setResult(
        await api<ScanResult>(
          "/scan",
          { method: "POST", body: JSON.stringify(body) },
          await currentToken(),
        ),
      );
    } catch (e) {
      setError(
        t(
          (e instanceof ApiError
            ? e.message
            : e instanceof Error && e.message === "photoFailed"
              ? "photoFailed"
              : "requestFailed") as TranslationKey,
        ),
      );
    } finally {
      setBusy("");
    }
  }

  return (
    <div className="page card scan-card">
      {scanning ? (
        <Suspense fallback={<p role="status">{t("loading")}</p>}>
          <Scanner onScan={onScan} onClose={() => setScanning(false)} />
        </Suspense>
      ) : (
        <button className="primary big" onClick={() => setScanning(true)}>
          {t("openCamera")}
        </button>
      )}

      <label>
        {t("barcode")}
        <textarea
          value={visible(barcode)}
          onChange={(e) => setBarcode(fromVisible(e.target.value))}
          rows={2}
        />
        <small>{t("separator")}</small>
      </label>
      <div className="chips">
        {SAMPLES.map((s) => (
          <button key={s.label} className="chip" onClick={() => setBarcode(s.barcode())}>
            {t(s.label)}
          </button>
        ))}
        <button className="chip" onClick={() => setBarcode(pharmaBarcode(freshSerial()))}>
          {t("newSerial")}
        </button>
      </div>

      <label>
        {t("eventType")}
        <select value={eventType} onChange={(e) => setEventType(e.target.value)}>
          <option value="verify">{t("verify")}</option>
          <option value="receive">{t("receive")}</option>
          <option value="dispense">{t("dispense")}</option>
          <option value="ship">{t("ship")}</option>
        </select>
      </label>

      <label>
        {t("location")}
        <select value={place} onChange={(e) => setPlace(e.target.value)}>
          <option value="gps">{t("gps")}</option>
          {Object.keys(DEMO_PLACES).map((p) => (
            <option key={p} value={p}>
              {t("demoPlace")} {p}
            </option>
          ))}
        </select>
      </label>

      <label>
        {t("photo")}
        <small>{t("photoHint")}</small>
        <input
          type="file"
          accept="image/*"
          capture="environment"
          onChange={(e) => setPhoto(e.target.files?.[0] ?? null)}
        />
      </label>

      <button className="primary big" disabled={!barcode.trim() || !!busy} onClick={submit}>
        {t("verifyPack")}
      </button>
      {busy && (
        <p role="status" className="hint">
          {busy}
        </p>
      )}
      {notice && <p className="hint">{t("noLocation")}</p>}
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      {result && (
        <ResultCard
          result={result}
          onHistory={() => onHistory(result.product.gtin!, result.product.serial!)}
        />
      )}
    </div>
  );
}
