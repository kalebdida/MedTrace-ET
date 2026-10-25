import { useEffect, useRef, useState } from "react";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import { api, currentToken, type AuditEvent, type History } from "./api";

function CloneMap({ events }: { events: AuditEvent[] }) {
  const el = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const located = events.filter((e) => e.location);
    if (!el.current || located.length === 0) return;
    const map = L.map(el.current);
    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      attribution: "© OpenStreetMap contributors",
    }).addTo(map);
    const byId = new Map(events.map((e) => [e.event_id, e]));
    for (const e of located) {
      const { lat, lon } = e.location!;
      L.circleMarker([lat, lon], { radius: 8, color: e.verdict === "FAIL" ? "#dc2626" : "#0f766e" })
        .addTo(map)
        .bindPopup(`#${e.seq} ${e.site_id ?? ""}<br>${new Date(e.scanned_at).toLocaleString()}<br>${e.verdict}`);
      // Draw the impossible journey the clone detector found.
      for (const f of e.flags ?? []) {
        const prior = byId.get(String(f.details?.prior_event_id ?? ""));
        if (f.code === "IMPOSSIBLE_TRAVEL" && prior?.location) {
          L.polyline([[prior.location.lat, prior.location.lon], [lat, lon]], { color: "#dc2626", dashArray: "6" }).addTo(map);
        }
      }
    }
    map.fitBounds(L.latLngBounds(located.map((e) => [e.location!.lat, e.location!.lon] as [number, number])).pad(0.3), {
      maxZoom: 12,
    });
    return () => {
      map.remove();
    };
  }, [events]);
  return <div ref={el} className="map" />;
}

export function HistoryPage({ initial }: { initial?: { gtin: string; serial: string } }) {
  const [gtin, setGtin] = useState(initial?.gtin ?? "");
  const [serial, setSerial] = useState(initial?.serial ?? "");
  const [history, setHistory] = useState<History | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function load(g = gtin, s = serial) {
    setError("");
    setBusy(true);
    try {
      const q = new URLSearchParams({ gtin: g.trim(), serial: s.trim() });
      setHistory(await api<History>(`/history?${q}`, {}, await currentToken()));
    } catch (e) {
      setHistory(null);
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => {
    if (initial) load(initial.gtin, initial.serial);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initial]);

  return (
    <div className="page">
      <label>GTIN<input value={gtin} onChange={(e) => setGtin(e.target.value)} inputMode="numeric" /></label>
      <label>Serial<input value={serial} onChange={(e) => setSerial(e.target.value)} /></label>
      <button className="primary" disabled={!gtin || !serial || busy} onClick={() => load()}>
        {busy ? "Loading…" : "Show history"}
      </button>
      {error && <p className="error">{error}</p>}
      {history && (
        <>
          <p className={`badge ${history.chain.valid ? "ok" : "bad"}`}>
            {history.chain.valid
              ? `✓ Audit chain intact (${history.scan_count} records)`
              : `✗ Audit chain TAMPERED at record #${history.chain.broken_at_seq}`}
          </p>
          <CloneMap events={history.events} />
          <ol className="timeline">
            {history.events.map((e) => (
              <li key={e.seq} className={e.verdict.toLowerCase()}>
                <strong>#{e.seq} {e.event_type}</strong> at {e.site_id ?? "unknown site"}
                <br />
                <small>{new Date(e.scanned_at).toLocaleString()} · {e.verdict}</small>
                {(e.flags ?? []).filter((f) => f.clone_indicator).map((f) => (
                  <div key={f.code} className="error small">{f.message}</div>
                ))}
              </li>
            ))}
          </ol>
        </>
      )}
    </div>
  );
}
