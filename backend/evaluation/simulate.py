"""Synthetic Ethiopian medicine-distribution scans for evaluating clone detection.

There is no public dataset of pharmaceutical serial scans in Ethiopia, so this
script generates one from explicit assumptions (listed in README.md) and runs
every scan through the production detector (medtrace.velocity). It produces:

  results.md                 detection and false-alarm rates per speed limit
  data/scan_features.csv     one labelled row per scan, with the same
                             travel_features the backend stores, as training
                             and test data for the routing-anomaly model

Run from backend/:  python -m evaluation.simulate
"""

from __future__ import annotations

import argparse
import csv
import math
import random
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from medtrace.velocity import GeoPoint, ScanObservation, VelocityConfig, assess_clone_risk, haversine_km

# Approximate city-centre coordinates.
CITIES = {
    "Addis Ababa": (9.0108, 38.7613),
    "Adama": (8.5400, 39.2700),
    "Bishoftu": (8.7525, 38.9785),
    "Hawassa": (7.0621, 38.4764),
    "Dire Dawa": (9.6009, 41.8501),
    "Harar": (9.3126, 42.1227),
    "Jijiga": (9.3500, 42.8000),
    "Dessie": (11.1300, 39.6333),
    "Mekelle": (13.4967, 39.4753),
    "Bahir Dar": (11.5742, 37.3614),
    "Gondar": (12.6030, 37.4521),
    "Jimma": (7.6739, 36.8344),
    "Nekemte": (9.0893, 36.5554),
    "Arba Minch": (6.0333, 37.5500),
}
AIR_FREIGHT_CITIES = {"Dire Dawa", "Jijiga", "Mekelle", "Bahir Dar", "Gondar", "Jimma", "Arba Minch"}
ROAD_FACTOR = 1.3  # road distance / straight-line distance
PHARMACIES_PER_CITY = 20
HISTORY_LIMIT = 25  # matches the backend default
THRESHOLDS_KMH = (60, 80, 100, 120, 150, 200, 300)
DEFAULT_KMH = 120
START = datetime(2026, 1, 1, tzinfo=timezone.utc)


@dataclass(frozen=True)
class SimScan:
    serial: str
    city: str
    is_clone: bool
    obs: ScanObservation


class Simulator:
    def __init__(self, seed: int):
        self.rng = random.Random(seed)
        self._sites: dict[tuple, tuple[str, tuple[float, float]]] = {}
        self._events = 0

    # --- world ---------------------------------------------------------------

    def site(self, kind: str, city: str, n: int) -> tuple[str, tuple[float, float]]:
        """A fixed premises: id and coordinates within a few km of the city centre."""
        key = (kind, city, n)
        if key not in self._sites:
            lat, lon = CITIES[city]
            point = _offset(lat, lon, self.rng.uniform(0, 4), self.rng.uniform(0, 2 * math.pi))
            self._sites[key] = (f"{kind}-{city.upper().replace(' ', '')}-{n:02d}", point)
        return self._sites[key]

    def gps_fix(self, point: tuple[float, float]) -> GeoPoint:
        rng = self.rng
        r = rng.random()
        if r < 0.80:  # good GPS fix
            error_m, accuracy = abs(rng.gauss(0, 15)), rng.uniform(5, 30)
        elif r < 0.97:  # network-based fix, accuracy reported honestly
            error_m = rng.uniform(100, 1500)
            accuracy = error_m * rng.uniform(1.0, 1.5)
        else:  # bad fix that under-reports its error (multipath, stale fix)
            error_m, accuracy = rng.uniform(2000, 5000), rng.uniform(10, 50)
        lat, lon = _offset(*point, error_m / 1000, rng.uniform(0, 2 * math.pi))
        return GeoPoint(lat, lon, accuracy)

    def transit_hours(self, a: str, b: str) -> float:
        rng = self.rng
        km = _city_km(a, b)
        if km < 1:
            return rng.uniform(0.5, 4)  # delivery within the city
        if a == "Addis Ababa" and b in AIR_FREIGHT_CITIES and rng.random() < 0.05:
            return rng.uniform(5, 12)  # express air freight, door to door
        return km * ROAD_FACTOR / rng.uniform(35, 65) + rng.uniform(1, 12)  # truck + loading

    def nearby_city(self, city: str) -> str:
        options = [c for c in CITIES if c != city and _city_km(c, city) <= 300]
        return self.rng.choice(options) if options else city

    def scan(self, serial: str, event_type: str, site: tuple, city: str, at: datetime, is_clone: bool) -> SimScan:
        self._events += 1
        site_id, point = site
        obs = ScanObservation(f"evt-{self._events}", at, event_type, site_id, self.gps_fix(point))
        return SimScan(serial, city, is_clone, obs)

    # --- journeys --------------------------------------------------------------

    def genuine_journey(self, serial: str) -> list[SimScan]:
        """Importer (Addis) -> regional wholesaler -> pharmacy -> patient."""
        rng = self.rng
        t = START + timedelta(days=rng.uniform(0, 300))
        region = rng.choice(list(CITIES))
        pharmacy_city = region if rng.random() < 0.7 else self.nearby_city(region)
        importer = self.site("IMP", "Addis Ababa", 0)
        wholesaler = self.site("WH", region, rng.randrange(2))
        pharmacy = self.site("PH", pharmacy_city, rng.randrange(PHARMACIES_PER_CITY))

        scans = [self.scan(serial, "ship", importer, "Addis Ababa", t, False)]
        t += timedelta(hours=self.transit_hours("Addis Ababa", region))
        scans.append(self.scan(serial, "receive", wholesaler, region, t, False))
        t += timedelta(days=rng.uniform(0.5, 21))
        scans.append(self.scan(serial, "ship", wholesaler, region, t, False))
        t += timedelta(hours=self.transit_hours(region, pharmacy_city))
        scans.append(self.scan(serial, "receive", pharmacy, pharmacy_city, t, False))
        for _ in range(rng.choice((0, 0, 1, 2))):  # spot checks on the shelf
            t += timedelta(days=rng.uniform(0.01, 10))
            scans.append(self.scan(serial, "verify", pharmacy, pharmacy_city, t, False))
        if rng.random() < 0.9:
            t += timedelta(days=rng.uniform(0.02, 45))
            scans.append(self.scan(serial, "dispense", pharmacy, pharmacy_city, t, False))
            if rng.random() < 0.05:  # pharmacist re-checks the pack a few minutes later
                t += timedelta(minutes=rng.uniform(0.5, 5))
                scans.append(self.scan(serial, "verify", pharmacy, pharmacy_city, t, False))
        return scans

    def clone_journey(self, serial: str, genuine: list[SimScan]) -> tuple[str, list[SimScan]]:
        """The serial copied onto a batch of counterfeit packs released to other pharmacies."""
        rng = self.rng
        anchor = [s for s in genuine if s.obs.event_type == "receive"][-1]
        scenario = "other_city" if rng.random() < 0.75 else "same_city"
        far_cities = [c for c in CITIES if _city_km(c, anchor.city) >= 100]
        release = anchor.obs.scanned_at + timedelta(days=rng.uniform(-30, 60))

        scans = []
        for _ in range(rng.choice((1, 1, 2, 3, 4))):  # copies of the serial in circulation
            if scenario == "other_city":
                city = rng.choice(far_cities)
                pharmacy = self.site("PH", city, rng.randrange(PHARMACIES_PER_CITY))
            else:
                city = anchor.city
                choices = [n for n in range(PHARMACIES_PER_CITY) if self.site("PH", city, n)[0] != anchor.obs.site_id]
                pharmacy = self.site("PH", city, rng.choice(choices))
            t = release + timedelta(days=rng.uniform(0, 3))  # a batch reaches shelves within days
            events = [e for e, p in (("receive", 0.6), ("verify", 0.5), ("dispense", 0.8)) if rng.random() < p]
            for event_type in events or ["verify"]:
                scans.append(self.scan(serial, event_type, pharmacy, city, t, True))
                t += timedelta(days=rng.uniform(0.01, 20))
        return scenario, scans


def generate(serials: int, clone_rate: float, seed: int):
    """Returns {serial: scans in time order} and {serial: scenario}."""
    sim = Simulator(seed)
    journeys, scenario = {}, {}
    for i in range(serials):
        serial = f"SN{i:06d}"
        scans = sim.genuine_journey(serial)
        scenario[serial] = "genuine"
        if sim.rng.random() < clone_rate:
            scenario[serial], copies = sim.clone_journey(serial, scans)
            scans += copies
        journeys[serial] = sorted(scans, key=lambda s: s.obs.scanned_at)
    return journeys, scenario


def evaluate(journeys: dict, scenario: dict, max_speed_kmh: float, rows: list | None = None) -> dict:
    """Replay every serial's scans through the detector, in time order."""
    config = VelocityConfig(max_speed_kmh=max_speed_kmh, min_distance_km=2.0)
    flagged: set[str] = set()
    before_harm: set[str] = set()  # caught no later than the first counterfeit dispense
    first_rule: Counter = Counter()  # rule behind the first alert on each cloned serial
    false_alarm_causes: Counter = Counter()
    for serial, scans in journeys.items():
        history: list[ScanObservation] = []
        harm_at = min((s.obs.scanned_at for s in scans if s.is_clone and s.obs.event_type == "dispense"), default=None)
        for s in scans:
            result = assess_clone_risk(s.obs, history[-HISTORY_LIMIT:], config)
            if result.clone_suspected and serial not in flagged:
                flagged.add(serial)
                codes = {f.code for f in result.flags if f.clone_indicator}
                if scenario[serial] == "genuine":
                    false_alarm_causes.update(codes)
                else:
                    first_rule["IMPOSSIBLE_TRAVEL" if "IMPOSSIBLE_TRAVEL" in codes else "dispense rules"] += 1
                    if harm_at is None or s.obs.scanned_at <= harm_at:
                        before_harm.add(serial)
            if rows is not None:
                rows.append(_row(s, scenario[serial], result))
            history.append(s.obs)

    def rate(group: list[str], hits: set[str]) -> float:
        return sum(s in hits for s in group) / len(group) if group else float("nan")

    by_scenario = {name: [s for s, sc in scenario.items() if sc == name] for name in ("other_city", "same_city", "genuine")}
    cloned = by_scenario["other_city"] + by_scenario["same_city"]
    true_alarms = sum(s in flagged for s in cloned)
    return {
        "max_speed_kmh": max_speed_kmh,
        "detected": rate(cloned, flagged),
        "detected_other_city": rate(by_scenario["other_city"], flagged),
        "detected_same_city": rate(by_scenario["same_city"], flagged),
        "detected_before_harm": rate(cloned, before_harm),
        "false_alarm_rate": rate(by_scenario["genuine"], flagged),
        "precision": true_alarms / len(flagged) if flagged else float("nan"),
        "first_rule": dict(first_rule),
        "false_alarm_causes": dict(false_alarm_causes),
    }


def _row(s: SimScan, scenario: str, result) -> dict:
    return {
        "serial": s.serial,
        "event_id": s.obs.event_id,
        "scanned_at": s.obs.scanned_at.isoformat(),
        "event_type": s.obs.event_type,
        "site_id": s.obs.site_id,
        "city": s.city,
        "lat": round(s.obs.location.lat, 6),
        "lon": round(s.obs.location.lon, 6),
        "accuracy_m": round(s.obs.location.accuracy_m, 1),
        **result.features,
        "rule_flagged": int(result.clone_suspected),
        "is_clone_scan": int(s.is_clone),
        "serial_cloned": int(scenario != "genuine"),
        "scenario": scenario,
    }


def _offset(lat: float, lon: float, km: float, bearing: float) -> tuple[float, float]:
    return (
        lat + km * math.cos(bearing) / 111.32,
        lon + km * math.sin(bearing) / (111.32 * math.cos(math.radians(lat))),
    )


def _city_km(a: str, b: str) -> float:
    return haversine_km(*CITIES[a], *CITIES[b])


def _pct(x: float) -> str:
    return "n/a" if math.isnan(x) else f"{100 * x:.1f}%"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--serials", type=int, default=3000)
    parser.add_argument("--clone-rate", type=float, default=0.10)
    parser.add_argument("--seed", type=int, default=2026)
    parser.add_argument("--out", type=Path, default=Path(__file__).parent)
    args = parser.parse_args()

    journeys, scenario = generate(args.serials, args.clone_rate, args.seed)
    rows: list[dict] = []
    results = [evaluate(journeys, scenario, kmh, rows if kmh == DEFAULT_KMH else None) for kmh in THRESHOLDS_KMH]

    counts = Counter(scenario.values())
    lines = [
        "# Clone-detection evaluation (synthetic data)",
        "",
        f"Generated by `python -m evaluation.simulate --serials {args.serials} "
        f"--clone-rate {args.clone_rate} --seed {args.seed}`.",
        "",
        f"{args.serials} serialised packs, {sum(len(v) for v in journeys.values())} scans; "
        f"{counts['other_city']} cloned into another city, {counts['same_city']} cloned within the same city, "
        f"{counts['genuine']} genuine. Minimum travel distance 2 km, last {HISTORY_LIMIT} scans compared.",
        "",
        "| Max plausible speed | Cloned packs caught | other city | same city "
        "| Caught before a counterfeit was dispensed | Genuine packs falsely flagged | Precision |",
        "|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for r in results:
        marker = " (default)" if r["max_speed_kmh"] == DEFAULT_KMH else ""
        lines.append(
            f"| {r['max_speed_kmh']} km/h{marker} | {_pct(r['detected'])} | {_pct(r['detected_other_city'])} "
            f"| {_pct(r['detected_same_city'])} | {_pct(r['detected_before_harm'])} "
            f"| {_pct(r['false_alarm_rate'])} | {_pct(r['precision'])} |"
        )
    default = next(r for r in results if r["max_speed_kmh"] == DEFAULT_KMH)
    rules = ", ".join(f"{rule} {n}" for rule, n in sorted(default["first_rule"].items())) or "none"
    causes = ", ".join(f"{code} x{n}" for code, n in sorted(default["false_alarm_causes"].items())) or "none"
    lines += [
        "",
        f"At {DEFAULT_KMH} km/h, first alert per caught clone came from: {rules}.",
        f"False-alarm flags at {DEFAULT_KMH} km/h: {causes}.",
        "",
    ]

    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "results.md").write_text("\n".join(lines))
    data_dir = args.out / "data"
    data_dir.mkdir(exist_ok=True)
    with open(data_dir / "scan_features.csv", "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print("\n".join(lines))
    print(f"Wrote {args.out / 'results.md'} and {data_dir / 'scan_features.csv'} ({len(rows)} rows)")


if __name__ == "__main__":
    main()
