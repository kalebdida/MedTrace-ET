import { useEffect, useRef } from "react";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import type { AuditEvent } from "./api";
export default function CloneMap({ events }: { events: AuditEvent[] }) {
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
        .bindPopup(
          Object.assign(document.createElement("span"), {
            textContent: `#${e.seq} ${e.site_id ?? ""} · ${new Date(e.scanned_at).toLocaleString()} · ${e.verdict}`,
          }),
        );
      // Draw the impossible journey the clone detector found.
      for (const f of e.flags ?? []) {
        const prior = byId.get(String(f.details?.prior_event_id ?? ""));
        if (f.code === "IMPOSSIBLE_TRAVEL" && prior?.location) {
          L.polyline(
            [
              [prior.location.lat, prior.location.lon],
              [lat, lon],
            ],
            { color: "#dc2626", dashArray: "6" },
          ).addTo(map);
        }
      }
    }
    map.fitBounds(
      L.latLngBounds(
        located.map((e) => [e.location!.lat, e.location!.lon] as [number, number]),
      ).pad(0.3),
      {
        maxZoom: 12,
      },
    );
    return () => {
      map.remove();
    };
  }, [events]);
  return <div ref={el} className="map" />;
}
