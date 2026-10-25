import { useEffect, useRef } from "react";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import type { AuditEvent } from "./api";
import { Icon } from "./Icon";
import { useI18n } from "./i18n";

export default function CloneMap({ events }: { events: AuditEvent[] }) {
  const { t } = useI18n();
  const el = useRef<HTMLDivElement>(null);
  const located = events.filter((e) => e.location);

  useEffect(() => {
    const loc = events.filter((e) => e.location);
    if (!el.current || loc.length === 0) return;
    const map = L.map(el.current);
    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      attribution: "© OpenStreetMap contributors",
    }).addTo(map);

    const byId = new Map(events.map((e) => [e.event_id, e]));
    let frameId = 0;

    for (const e of loc) {
      const { lat, lon } = e.location!;
      const isFail = e.verdict === "FAIL";
      L.circleMarker([lat, lon], {
        radius: isFail ? 10 : 8,
        color: isFail ? "#dc2626" : "#0b4f4a",
        fillColor: isFail ? "#ef4444" : "#14b8a6",
        fillOpacity: 0.85,
        weight: 3,
      })
        .addTo(map)
        .bindPopup(
          Object.assign(document.createElement("span"), {
            textContent: `#${e.seq} ${e.site_id ?? ""} · ${new Date(e.scanned_at).toLocaleString()} · ${e.verdict}`,
          }),
        );

      // Draw and animate the impossible journey the clone detector found.
      for (const f of e.flags ?? []) {
        const prior =
          byId.get(String(f.details?.prior_event_id ?? "")) ??
          loc.find((prev) => prev.seq < e.seq && prev.location);
        if ((f.code === "IMPOSSIBLE_TRAVEL" || f.clone_indicator) && prior?.location) {
          const start: [number, number] = [prior.location.lat, prior.location.lon];
          const end: [number, number] = [lat, lon];

          // Base faint trajectory track
          L.polyline([start, end], {
            color: "#fca5a5",
            weight: 2,
            dashArray: "4 6",
            opacity: 0.65,
          }).addTo(map);

          const reduced = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false;
          const activeLine = L.polyline(reduced ? [start, end] : [start, start], {
            color: "#dc2626",
            weight: 4,
            dashArray: "8 6",
            className: "clone-journey-line",
          }).addTo(map);

          if (!reduced) {
            const t0 = performance.now();
            const duration = 650;
            const step = (now: number) => {
              const p = Math.min(1, (now - t0) / duration);
              const eased = 1 - Math.pow(1 - p, 3);
              const curLat = start[0] + (end[0] - start[0]) * eased;
              const curLon = start[1] + (end[1] - start[1]) * eased;
              activeLine.setLatLngs([start, [curLat, curLon]]);
              if (p < 1) frameId = requestAnimationFrame(step);
            };
            frameId = requestAnimationFrame(step);
          }
        }
      }
    }

    map.fitBounds(
      L.latLngBounds(loc.map((e) => [e.location!.lat, e.location!.lon] as [number, number])).pad(
        0.32,
      ),
      {
        maxZoom: 12,
      },
    );
    return () => {
      cancelAnimationFrame(frameId);
      map.remove();
    };
  }, [events]);

  const hasCloneHop = located.some((e) =>
    (e.flags ?? []).some((f) => f.code === "IMPOSSIBLE_TRAVEL" || f.clone_indicator),
  );

  return (
    <div className="map-wrapper">
      <div ref={el} className="map" />
      {located.length >= 2 && (
        <div className={`map-route-bar ${hasCloneHop ? "clone-active" : ""}`}>
          <span className="map-route-tag">
            {hasCloneHop && <Icon name="cross" size={14} />}
            <span>{hasCloneHop ? t("routeAnimatedLabel") : t("map")}</span>
          </span>
          <div className="map-route-stops mono">
            {located.map((e, idx) => (
              <span key={e.seq} className="map-stop-item">
                {idx > 0 && (
                  <span className="map-stop-arrow" aria-hidden="true">
                    →
                  </span>
                )}
                <strong>#{e.seq}</strong> {e.site_id ?? t("unknownSite")} ({e.verdict})
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
