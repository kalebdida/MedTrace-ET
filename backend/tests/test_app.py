import json

import pytest

import app
from medtrace.audit import AuditLog
from tests.conftest import ADAMA, ADDIS_ABABA, DESSIE, GTIN, ago, call, http_event, iso, pharma_barcode, rest_event


def scan(barcode=None, location=ADAMA, minutes_ago=0, **fields):
    body = {
        "barcode": barcode or pharma_barcode(),
        "location": location,
        "scanned_at": iso(ago(minutes=minutes_ago)),
        **fields,
    }
    return call(http_event("POST", "/scan", body))


def flag_codes(body):
    return [f["code"] for f in body["flags"]]


# --- /scan ------------------------------------------------------------------

def test_first_scan_of_genuine_pack_passes(aws):
    status, body = scan(site_id="PH-ADAMA-001", device_id="android-1")
    assert status == 200
    assert body["verdict"] == "PASS"
    assert body["clone_suspected"] is False
    assert body["product"]["gtin"] == GTIN
    assert body["product"]["serialization_complete"] is True
    assert body["audit"]["seq"] == 1
    assert body["audit"]["prev_hash"] == "0" * 64
    assert body["travel"]["features"]["prior_scans"] == 0
    assert body["alert_sent"] is False
    assert aws["alerts"]() == []

    item = aws["table"].get_item(Key={"pk": f"SGTIN#{GTIN}#SN0001", "sk": "0000000001"})["Item"]
    assert item["site_id"] == "PH-ADAMA-001"
    assert item["biz_step"] == "inspecting"
    assert item["record_hash"] == body["audit"]["record_hash"]


def test_cloned_serial_in_another_city_is_intercepted_and_alerted(aws):
    scan(location=ADAMA, minutes_ago=50, site_id="PH-ADAMA-001", event_type="receive")
    status, body = scan(location=DESSIE, site_id="PH-DESSIE-007")

    assert status == 200
    assert body["verdict"] == "FAIL"
    assert body["clone_suspected"] is True
    assert flag_codes(body) == ["IMPOSSIBLE_TRAVEL"]
    assert body["travel"]["legs"][0]["prior_site_id"] == "PH-ADAMA-001"
    assert body["audit"]["seq"] == 2
    assert body["alert_sent"] is True

    [envelope] = aws["alerts"]()
    assert envelope["Subject"] == "MedTrace-ET ALERT: cloned barcode intercepted"
    alert = json.loads(envelope["Message"])
    assert alert["alert_type"] == "CLONED_BARCODE"
    assert (alert["gtin"], alert["serial"], alert["site_id"]) == (GTIN, "SN0001", "PH-DESSIE-007")
    assert alert["flags"][0]["code"] == "IMPOSSIBLE_TRAVEL"
    assert alert["audit"]["record_hash"] == body["audit"]["record_hash"]


def test_normal_supply_chain_journey_passes(aws):
    scan(location=ADDIS_ABABA, minutes_ago=24 * 60, event_type="ship", site_id="WH-ADDIS")
    scan(location=ADAMA, minutes_ago=18 * 60, event_type="receive", site_id="PH-ADAMA-001")
    status, body = scan(location=ADAMA, event_type="dispense", site_id="PH-ADAMA-001")
    assert body["verdict"] == "PASS"
    assert body["audit"]["seq"] == 3
    assert aws["alerts"]() == []


def test_dispensed_pack_reappearing_is_a_clone(aws):
    scan(location=ADAMA, minutes_ago=24 * 60, event_type="dispense", site_id="PH-ADAMA-001")
    _, body = scan(location=ADDIS_ABABA, event_type="receive", site_id="PH-ADDIS-020")
    assert flag_codes(body) == ["DISPENSED_PACK_RESURFACED"]
    assert body["alert_sent"] is True


def test_second_dispense_is_a_clone(aws):
    scan(minutes_ago=60, event_type="dispense", site_id="PH-ADAMA-001")
    _, body = scan(event_type="dispense", site_id="PH-ADAMA-001")
    assert flag_codes(body) == ["ALREADY_DISPENSED"]
    assert body["verdict"] == "FAIL"


def test_invalid_barcode_fails_and_is_still_logged(aws):
    status, body = scan(barcode="0109506000134353")
    assert status == 200
    assert body["verdict"] == "FAIL"
    assert flag_codes(body) == ["INVALID_BARCODE"]
    assert body["travel"] is None
    assert body["audit"]["pk"].startswith("UNIDENTIFIED#")
    assert body["product"]["errors"][0]["code"] == "BAD_CHECK_DIGIT"


def test_expired_pack_fails(aws):
    _, body = scan(barcode=pharma_barcode(expiry="200131"))
    assert flag_codes(body) == ["EXPIRED"]
    assert body["verdict"] == "FAIL"
    assert body["clone_suspected"] is False


def test_unserialised_pack_warns(aws):
    _, body = scan(barcode=f"01{GTIN}17301231")
    assert body["verdict"] == "WARN"
    assert flag_codes(body) == ["INCOMPLETE_SERIALIZATION"]
    assert body["audit"]["pk"].startswith("UNIDENTIFIED#")


def test_device_clock_ahead_falls_back_to_server_time(aws):
    _, body = scan(minutes_ago=-60)
    assert flag_codes(body) == ["CLOCK_SKEW"]
    assert body["verdict"] == "PASS"


def test_scan_without_location_skips_travel_check(aws):
    scan(location=ADAMA, minutes_ago=10)
    _, body = scan(location=None)
    assert body["verdict"] == "PASS"
    assert body["travel"]["legs"] == []


def test_concurrent_scan_is_seen_on_retry(aws, monkeypatch):
    # The Dessie scan reads history before the Adama scan is written, then
    # loses the race to append; on retry it must see Adama and flag a clone.
    services = app.get_services()
    real_recent = services.audit.recent
    calls = {"n": 0}

    def stale_then_fresh(pk, limit):
        calls["n"] += 1
        if calls["n"] == 1:
            stale = real_recent(pk, limit)
            AuditLog(aws["table"]).append(pk, None, {
                "event_id": "racing-scan",
                "scanned_at": iso(ago(minutes=1)),
                "event_type": "verify",
                "site_id": "PH-ADAMA-001",
                "location": ADAMA,
            })
            return stale
        return real_recent(pk, limit)

    monkeypatch.setattr(services.audit, "recent", stale_then_fresh)
    _, body = scan(location=DESSIE, site_id="PH-DESSIE-007")
    assert calls["n"] == 2
    assert body["audit"]["seq"] == 2
    assert flag_codes(body) == ["IMPOSSIBLE_TRAVEL"]


def test_alert_failure_does_not_lose_the_scan(aws, monkeypatch):
    monkeypatch.setenv("ALERT_TOPIC_ARN", aws["topic_arn"] + "-missing")
    monkeypatch.setattr(app, "_services", None)
    scan(location=ADAMA, minutes_ago=30)
    status, body = scan(location=DESSIE)
    assert status == 200
    assert body["clone_suspected"] is True
    assert body["alert_sent"] is False


def test_scan_emits_cloudwatch_emf_metrics(aws, capsys):
    scan(location=ADAMA, minutes_ago=30)
    capsys.readouterr()
    scan(location=DESSIE)
    emf = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert emf["_aws"]["CloudWatchMetrics"][0]["Namespace"] == "MedTraceET"
    assert emf["CloneAlerts"] == 1
    assert emf["ScansProcessed"] == 1
    assert emf["verdict"] == "FAIL"
    assert emf["lat"] == DESSIE["lat"]


@pytest.mark.parametrize("body, message", [
    ({}, "barcode is required"),
    ({"barcode": 42}, "barcode is required"),
    ({"barcode": "x" * 513}, "at most 512"),
    ({"barcode": "01", "event_type": "steal"}, "event_type must be one of"),
    ({"barcode": "01", "location": {"lat": 91, "lon": 38}}, "location.lat"),
    ({"barcode": "01", "location": {"lat": 9, "lon": "38"}}, "location.lon"),
    ({"barcode": "01", "location": {"lat": 9, "lon": 38, "accuracy_m": -1}}, "accuracy_m"),
    ({"barcode": "01", "location": [9, 38]}, "location must be an object"),
    ({"barcode": "01", "site_id": "PH 1; DROP"}, "site_id must be"),
    ({"barcode": "01", "scanned_at": "2026-10-22T09:00:00"}, "timezone offset"),
    ({"barcode": "01", "scanned_at": "yesterday"}, "ISO-8601"),
])
def test_scan_rejects_bad_requests(aws, body, message):
    status, resp = call(http_event("POST", "/scan", body))
    assert status == 400
    assert message in resp["error"]


@pytest.mark.parametrize("raw, status", [("not json", 400), ("[1, 2]", 400), ("{" + " " * 17000 + "}", 413)])
def test_malformed_bodies(aws, raw, status):
    assert call(http_event("POST", "/scan", raw))[0] == status


def test_scan_without_table_configured_is_unavailable(monkeypatch):
    monkeypatch.delenv("SCAN_TABLE_NAME", raising=False)
    monkeypatch.delenv("ALERT_TOPIC_ARN", raising=False)
    monkeypatch.setattr(app, "_services", None)
    status, body = call(http_event("POST", "/scan", {"barcode": pharma_barcode()}))
    assert status == 503
    monkeypatch.setattr(app, "_services", None)


# --- /history ---------------------------------------------------------------

def test_history_returns_verified_chain(aws):
    scan(location=ADDIS_ABABA, minutes_ago=600, event_type="ship", site_id="WH-ADDIS")
    scan(location=ADAMA, minutes_ago=60, event_type="receive", site_id="PH-ADAMA-001")
    status, body = call(http_event("GET", "/history", query={"gtin": GTIN, "serial": "SN0001"}))
    assert status == 200
    assert body["scan_count"] == 2
    assert body["chain"]["valid"] is True
    assert [e["site_id"] for e in body["events"]] == ["WH-ADDIS", "PH-ADAMA-001"]


def test_history_detects_tampering(aws):
    scan(location=ADDIS_ABABA, minutes_ago=600, site_id="WH-ADDIS")
    scan(location=ADAMA, minutes_ago=60, site_id="PH-ADAMA-001")
    pk = f"SGTIN#{GTIN}#SN0001"
    item = aws["table"].get_item(Key={"pk": pk, "sk": "0000000001"})["Item"]
    aws["table"].put_item(Item={**item, "site_id": "WH-FORGED"})

    _, body = call(http_event("GET", "/history", query={"gtin": GTIN, "serial": "SN0001"}))
    assert body["chain"] == {"valid": False, "length": 2, "broken_at_seq": 1, "reason": "record_modified"}


@pytest.mark.parametrize("query, status", [
    (None, 400),
    ({"gtin": GTIN}, 400),
    ({"gtin": "09506000134353", "serial": "SN1"}, 400),
    ({"gtin": GTIN, "serial": "SN 1"}, 400),
    ({"sscc": "123"}, 400),
    ({"gtin": GTIN, "serial": "NEVER-SCANNED"}, 404),
])
def test_history_validation(aws, query, status):
    assert call(http_event("GET", "/history", query=query))[0] == status


# --- /parse, /health and routing --------------------------------------------

def test_parse_endpoint_is_stateless(aws):
    status, body = call(http_event("POST", "/parse", {"barcode": pharma_barcode()}))
    assert status == 200
    assert body["valid"] is True
    assert body["serial"] == "SN0001"
    assert aws["table"].scan()["Count"] == 0


def test_rest_api_v1_event(aws):
    status, body = call(rest_event("POST", "/parse", {"barcode": pharma_barcode()}))
    assert status == 200
    assert body["gtin"] == GTIN


def test_http_api_named_stage_prefix_is_stripped(aws):
    status, body = call(http_event("GET", "/prod/health", stage="prod"))
    assert status == 200
    assert body == {"status": "ok", "audit_log_configured": True, "alerts_configured": True}


def test_base64_body(aws):
    event = http_event("POST", "/parse", {"barcode": pharma_barcode()}, base64_body=True)
    assert call(event)[0] == 200


def test_cors_preflight(aws):
    response = app.lambda_handler(http_event("OPTIONS", "/scan"), None)
    assert response["statusCode"] == 204
    assert response["headers"]["Access-Control-Allow-Origin"] == "*"


def test_unknown_route_and_wrong_method(aws):
    assert call(http_event("GET", "/nope"))[0] == 404
    assert call(http_event("GET", "/scan"))[0] == 405


def test_unexpected_errors_return_500_without_details(aws, monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("secret internals")

    monkeypatch.setattr(app.gs1, "parse", boom)
    status, body = call(http_event("POST", "/parse", {"barcode": pharma_barcode()}))
    assert status == 500
    assert body == {"error": "Internal server error", "request_id": "test-request-id"}
