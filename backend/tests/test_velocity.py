from datetime import datetime, timedelta, timezone

import pytest

from medtrace.velocity import GeoPoint, ScanObservation, VelocityConfig, assess_clone_risk, haversine_km
from tests.conftest import ADAMA, ADDIS_ABABA, DESSIE

T0 = datetime(2026, 10, 22, 8, 0, tzinfo=timezone.utc)
CONFIG = VelocityConfig(max_speed_kmh=120, min_distance_km=2)


def point(city, accuracy_m=None):
    return GeoPoint(city["lat"], city["lon"], accuracy_m)


def scan(event_id, minutes, city=None, event_type="verify", site_id=None, accuracy_m=None, location=None):
    return ScanObservation(
        event_id=event_id,
        scanned_at=T0 + timedelta(minutes=minutes),
        event_type=event_type,
        site_id=site_id,
        location=location or (point(city, accuracy_m) if city else None),
    )


def flag_codes(assessment):
    return [f.code for f in assessment.flags]


def test_haversine_known_distances():
    assert haversine_km(**_pair(ADDIS_ABABA, ADAMA)) == pytest.approx(76.6, abs=0.5)
    assert haversine_km(**_pair(ADAMA, DESSIE)) == pytest.approx(290, abs=5)
    assert haversine_km(9.0, 38.7, 9.0, 38.7) == 0


def _pair(a, b):
    return {"lat1": a["lat"], "lon1": a["lon"], "lat2": b["lat"], "lon2": b["lon"]}


def test_adama_to_dessie_in_one_hour_is_impossible():
    result = assess_clone_risk(
        scan("now", 60, DESSIE, site_id="PH-DESSIE"),
        [scan("before", 0, ADAMA, site_id="PH-ADAMA")],
        CONFIG,
    )
    assert flag_codes(result) == ["IMPOSSIBLE_TRAVEL"]
    assert result.clone_suspected
    details = result.flags[0].details
    assert details["prior_site_id"] == "PH-ADAMA"
    assert details["speed_kmh"] == pytest.approx(290, abs=5)
    assert result.features["impossible_legs"] == 1


def test_addis_to_adama_in_six_hours_is_plausible():
    result = assess_clone_risk(scan("now", 360, ADAMA), [scan("before", 0, ADDIS_ABABA)], CONFIG)
    assert result.flags == []
    assert not result.clone_suspected
    assert result.legs[0].speed_kmh == pytest.approx(76.6 / 6, abs=0.5)


def test_simultaneous_scans_in_two_cities_give_finite_speed():
    result = assess_clone_risk(scan("now", 0, DESSIE), [scan("before", 0, ADAMA)], CONFIG)
    assert flag_codes(result) == ["IMPOSSIBLE_TRAVEL"]
    assert result.legs[0].speed_kmh < float("inf")


def test_out_of_order_history_uses_absolute_time_gap():
    # A later scan uploaded first (offline device) is still compared correctly.
    result = assess_clone_risk(scan("now", 0, ADAMA), [scan("later", 30, DESSIE)], CONFIG)
    assert flag_codes(result) == ["IMPOSSIBLE_TRAVEL"]


def test_gps_accuracy_prevents_false_alarm():
    here = GeoPoint(9.0108, 38.7613, accuracy_m=2000)
    three_km_away = GeoPoint(9.0378, 38.7613, accuracy_m=2000)
    result = assess_clone_risk(
        scan("now", 1, location=three_km_away),
        [scan("before", 0, location=here)],
        CONFIG,
    )
    assert result.legs[0].distance_km == pytest.approx(3, abs=0.1)
    assert result.legs[0].effective_distance_km == 0
    assert result.flags == []


def test_short_hops_below_min_distance_never_flag():
    a = GeoPoint(9.0108, 38.7613)
    b = GeoPoint(9.0208, 38.7613)  # ~1.1 km
    result = assess_clone_risk(scan("now", 0, location=b), [scan("before", 0, location=a)], CONFIG)
    assert result.flags == []


def test_worst_leg_is_reported():
    history = [scan("addis", 0, ADDIS_ABABA), scan("adama", 50, ADAMA)]
    result = assess_clone_risk(scan("now", 60, DESSIE), history, CONFIG)
    assert result.flags[0].details["prior_event_id"] == "adama"
    assert result.flags[0].details["conflicting_scans"] == 2


def test_scans_without_location_are_skipped():
    result = assess_clone_risk(scan("now", 1), [scan("before", 0, ADAMA)], CONFIG)
    assert result.legs == []
    assert result.flags == []
    assert result.features["prior_scans"] == 1


def test_second_dispense_is_a_clone():
    history = [scan("d1", 0, ADAMA, "dispense", "PH-1")]
    result = assess_clone_risk(scan("now", 600, ADAMA, "dispense", "PH-1"), history, CONFIG)
    assert flag_codes(result) == ["ALREADY_DISPENSED"]
    assert result.clone_suspected


def test_dispensed_pack_resurfacing_elsewhere_is_a_clone():
    history = [scan("d1", 0, ADAMA, "dispense", "PH-1")]
    result = assess_clone_risk(scan("now", 24 * 60, ADDIS_ABABA, "receive", "WH-9"), history, CONFIG)
    assert flag_codes(result) == ["DISPENSED_PACK_RESURFACED"]
    assert result.clone_suspected


def test_rescan_after_dispense_at_same_site_only_warns():
    history = [scan("d1", 0, ADAMA, "dispense", "PH-1")]
    result = assess_clone_risk(scan("now", 5, ADAMA, "verify", "PH-1"), history, CONFIG)
    assert flag_codes(result) == ["PREVIOUSLY_DISPENSED"]
    assert not result.clone_suspected


def test_dispense_recorded_after_this_scan_is_ignored():
    # The wholesaler's receive scan arrives late from an offline phone.
    history = [scan("d1", 120, ADAMA, "dispense", "PH-1")]
    result = assess_clone_risk(scan("now", 0, ADAMA, "receive", "WH-1"), history, CONFIG)
    assert "DISPENSED_PACK_RESURFACED" not in flag_codes(result)


def test_unknown_place_does_not_accuse():
    history = [scan("d1", 0, event_type="dispense")]
    result = assess_clone_risk(scan("now", 60, event_type="verify"), history, CONFIG)
    assert flag_codes(result) == ["PREVIOUSLY_DISPENSED"]


def test_features_summarise_history():
    history = [
        scan("a", 0, ADDIS_ABABA, "receive", "WH-1"),
        scan("b", 300, ADAMA, "receive", "PH-1"),
    ]
    features = assess_clone_risk(scan("now", 360, ADAMA, "verify", "PH-1"), history, CONFIG).features
    assert features == {
        "prior_scans": 2,
        "distinct_sites": 2,
        "prior_dispenses": 0,
        "hours_since_nearest_scan": 1.0,
        "max_distance_km": pytest.approx(76.6, abs=0.5),
        "max_speed_kmh": pytest.approx(13, abs=1),
        "impossible_legs": 0,
    }
