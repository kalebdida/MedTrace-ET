"""Cloned-barcode detection from the scan history of one serial number.

A genuine pack exists in one place at a time and is dispensed once. When the
same GTIN + serial is seen in two places further apart than any vehicle could
travel in the time between the scans, or reappears after it was dispensed,
the code has been copied onto other packaging.

Distances are great-circle (haversine). Straight-line distance understates
the road distance, so the default speed limit is deliberately below highway
speeds. Each scan's reported GPS accuracy is subtracted from the distance so
an imprecise fix cannot by itself produce an alert.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime

from .flags import CRITICAL, WARNING, Flag

EARTH_RADIUS_KM = 6371.0088
# Floor the time gap at one second so simultaneous scans yield a finite speed.
MIN_GAP_HOURS = 1 / 3600


@dataclass(frozen=True)
class GeoPoint:
    lat: float
    lon: float
    accuracy_m: float | None = None


@dataclass(frozen=True)
class ScanObservation:
    event_id: str
    scanned_at: datetime
    event_type: str
    site_id: str | None = None
    location: GeoPoint | None = None


@dataclass(frozen=True)
class VelocityConfig:
    max_speed_kmh: float = 120.0
    min_distance_km: float = 2.0


@dataclass(frozen=True)
class TravelLeg:
    prior_event_id: str
    prior_site_id: str | None
    prior_scanned_at: datetime
    distance_km: float
    effective_distance_km: float
    hours: float
    speed_kmh: float
    impossible: bool

    def to_dict(self) -> dict:
        return {
            "prior_event_id": self.prior_event_id,
            "prior_site_id": self.prior_site_id,
            "prior_scanned_at": self.prior_scanned_at.isoformat(),
            "distance_km": round(self.distance_km, 2),
            "effective_distance_km": round(self.effective_distance_km, 2),
            "hours": round(self.hours, 4),
            "speed_kmh": round(self.speed_kmh, 1),
            "impossible": self.impossible,
        }


@dataclass
class CloneAssessment:
    legs: list[TravelLeg] = field(default_factory=list)
    flags: list[Flag] = field(default_factory=list)
    features: dict = field(default_factory=dict)

    @property
    def clone_suspected(self) -> bool:
        return any(f.clone_indicator for f in self.flags)


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = phi2 - phi1
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlmb / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(min(1.0, a)))


def travel_leg(current: ScanObservation, prior: ScanObservation, config: VelocityConfig) -> TravelLeg | None:
    if current.location is None or prior.location is None:
        return None
    a, b = current.location, prior.location
    distance = haversine_km(a.lat, a.lon, b.lat, b.lon)
    slack_km = ((a.accuracy_m or 0.0) + (b.accuracy_m or 0.0)) / 1000
    effective = max(0.0, distance - slack_km)
    hours = max(abs((current.scanned_at - prior.scanned_at).total_seconds()) / 3600, MIN_GAP_HOURS)
    speed = effective / hours
    # Two scans at the same registered site are not travel: any distance
    # between them is GPS error, often from fixes that under-report it.
    same_site = current.site_id is not None and current.site_id == prior.site_id
    return TravelLeg(
        prior_event_id=prior.event_id,
        prior_site_id=prior.site_id,
        prior_scanned_at=prior.scanned_at,
        distance_km=distance,
        effective_distance_km=effective,
        hours=hours,
        speed_kmh=speed,
        impossible=not same_site and effective >= config.min_distance_km and speed > config.max_speed_kmh,
    )


def assess_clone_risk(
    current: ScanObservation,
    history: list[ScanObservation],
    config: VelocityConfig,
) -> CloneAssessment:
    """Compare a new scan with earlier scans of the same serial."""
    history = [h for h in history if h.event_id != current.event_id]
    legs = [leg for prior in history if (leg := travel_leg(current, prior, config))]
    assessment = CloneAssessment(legs=legs)

    impossible = [leg for leg in legs if leg.impossible]
    if impossible:
        worst = max(impossible, key=lambda leg: leg.speed_kmh)
        where = f" at site {worst.prior_site_id}" if worst.prior_site_id else ""
        assessment.flags.append(Flag(
            "IMPOSSIBLE_TRAVEL",
            CRITICAL,
            f"This serial was also scanned {worst.distance_km:.0f} km away{where}, "
            f"{_human_duration(worst.hours)} apart. Travelling that far that fast "
            f"({worst.speed_kmh:.0f} km/h, limit {config.max_speed_kmh:.0f} km/h) is "
            "impossible, so the barcode has been cloned.",
            clone_indicator=True,
            details={**worst.to_dict(), "conflicting_scans": len(impossible)},
        ))

    dispense_flag = _dispense_flag(current, history, config)
    if dispense_flag:
        assessment.flags.append(dispense_flag)

    assessment.features = _features(current, history, legs)
    return assessment


def _dispense_flag(current: ScanObservation, history: list[ScanObservation], config: VelocityConfig) -> Flag | None:
    # Only dispenses that happened before this scan count; an older scan
    # uploaded late from an offline device must not trip this rule.
    dispensed = [h for h in history if h.event_type == "dispense" and h.scanned_at <= current.scanned_at]
    if not dispensed:
        return None
    last = max(dispensed, key=lambda h: h.scanned_at)
    details = {
        "dispensed_event_id": last.event_id,
        "dispensed_at": last.scanned_at.isoformat(),
        "dispensed_site_id": last.site_id,
    }
    if current.event_type == "dispense":
        return Flag(
            "ALREADY_DISPENSED",
            CRITICAL,
            f"This pack was already dispensed on {last.scanned_at:%Y-%m-%d %H:%M} UTC. "
            "A genuine pack is dispensed only once, so this barcode is cloned or reused.",
            clone_indicator=True,
            details=details,
        )
    if _different_place(current, last, config):
        return Flag(
            "DISPENSED_PACK_RESURFACED",
            CRITICAL,
            f"This pack was dispensed to a patient on {last.scanned_at:%Y-%m-%d %H:%M} UTC "
            "and has now appeared at another location, so the barcode is cloned.",
            clone_indicator=True,
            details=details,
        )
    return Flag(
        "PREVIOUSLY_DISPENSED",
        WARNING,
        "This pack was already dispensed at this site. Do not dispense it again.",
        details=details,
    )


def _different_place(a: ScanObservation, b: ScanObservation, config: VelocityConfig) -> bool:
    if a.site_id and b.site_id:
        return a.site_id != b.site_id
    if a.location and b.location:
        leg = travel_leg(a, b, config)
        return leg is not None and leg.effective_distance_km >= config.min_distance_km
    return False  # not enough information to accuse the pack


def _features(current: ScanObservation, history: list[ScanObservation], legs: list[TravelLeg]) -> dict:
    """Numeric summary of the serial's movement, for downstream anomaly models."""
    sites = {h.site_id for h in history if h.site_id} | ({current.site_id} if current.site_id else set())
    gaps = [abs((current.scanned_at - h.scanned_at).total_seconds()) / 3600 for h in history]
    return {
        "prior_scans": len(history),
        "distinct_sites": len(sites),
        "prior_dispenses": sum(1 for h in history if h.event_type == "dispense"),
        "hours_since_nearest_scan": round(min(gaps), 4) if gaps else None,
        "max_distance_km": round(max((leg.distance_km for leg in legs), default=0.0), 2),
        "max_speed_kmh": round(max((leg.speed_kmh for leg in legs), default=0.0), 1),
        "impossible_legs": sum(1 for leg in legs if leg.impossible),
    }


def _human_duration(hours: float) -> str:
    minutes = hours * 60
    if minutes < 1:
        return "less than a minute"
    if minutes < 120:
        return f"{minutes:.0f} min"
    if hours < 48:
        return f"{hours:.1f} h"
    return f"{hours / 24:.1f} days"
