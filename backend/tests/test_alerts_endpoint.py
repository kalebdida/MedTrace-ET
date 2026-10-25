import app
from tests.conftest import call, claims_for, http_event

INSPECTOR = {"sub": "inspector-1", "custom:role": "inspector"}


class FakeAlerts:
    """Stands in for the Postgres audit log's recent_alerts()."""

    def __init__(self, records, next_before=None):
        self.records, self.next_before, self.calls = records, next_before, []

    def recent_alerts(self, limit, before=None):
        self.calls.append((limit, before))
        return self.records[:limit], self.next_before


CLONE_RECORD = {
    "event_id": "e2", "received_at": "2026-10-25T10:00:00+00:00", "scanned_at": "2026-10-25T10:00:00+00:00",
    "event_type": "verify", "site_id": "PH-DESSIE-007", "site_source": "token", "actor": "u2",
    "location": {"lat": 11.13, "lon": 39.6333}, "gtin": "09506000134352", "serial": "S1", "batch": "B1",
    "verdict": "FAIL", "pk": "SGTIN#09506000134352#S1", "seq": 2, "record_hash": "h2",
    "barcode_raw": "]d2…", "travel_features": {"max_speed_kmh": 348.8},
    "flags": [
        {"code": "IMPOSSIBLE_TRAVEL", "severity": "critical", "message": "291 km in 50 min", "clone_indicator": True,
         "details": {"speed_kmh": 348.8}},
        {"code": "NEAR_EXPIRY", "severity": "warning", "message": "Expires soon", "clone_indicator": False},
    ],
}


def alerts(query=None, claims=INSPECTOR):
    return call(http_event("GET", "/alerts", query=query, claims=claims))


def use_fake(monkeypatch, fake):
    monkeypatch.setattr(app.get_services(), "audit", fake)


def test_requires_sign_in(aws):
    assert alerts(claims=None)[0] == 401


def test_pharmacists_cannot_list_alerts(aws):
    status, body = alerts(claims=claims_for("u", "PH-ADAMA-001"))
    assert status == 403
    assert "inspector" in body["error"]


def test_dynamodb_backend_reports_unsupported(aws):
    status, body = alerts()
    assert status == 501
    assert "/history" in body["error"]


def test_lists_clone_alerts_with_summary_only(aws, monkeypatch):
    fake = FakeAlerts([CLONE_RECORD], next_before="2026-10-25T09:00:00+00:00")
    use_fake(monkeypatch, fake)
    status, body = alerts({"limit": "5"})
    assert status == 200
    assert fake.calls == [(5, None)]
    assert body["next_before"] == "2026-10-25T09:00:00+00:00"
    [alert] = body["alerts"]
    assert alert["site_id"] == "PH-DESSIE-007" and alert["serial"] == "S1"
    assert alert["flags"] == [{"code": "IMPOSSIBLE_TRAVEL", "severity": "critical", "message": "291 km in 50 min"}]
    assert "barcode_raw" not in alert and "travel_features" not in alert


def test_default_limit_and_before_cursor(aws, monkeypatch):
    fake = FakeAlerts([])
    use_fake(monkeypatch, fake)
    assert alerts({"before": "2026-10-25T12:00:00+03:00"})[0] == 200
    assert fake.calls == [(20, "2026-10-25T09:00:00+00:00")]


def test_rejects_bad_parameters(aws, monkeypatch):
    use_fake(monkeypatch, FakeAlerts([]))
    for query in ({"limit": "0"}, {"limit": "101"}, {"limit": "ten"}, {"before": "yesterday"}, {"before": "2026-10-25T12:00:00"}):
        status, body = alerts(query)
        assert status == 400, query


def test_cognito_inspectors_group(aws, monkeypatch):
    use_fake(monkeypatch, FakeAlerts([]))
    for groups in (["inspectors"], "[inspectors]", "admins,inspectors"):
        assert alerts(claims={"sub": "u", "cognito:groups": groups})[0] == 200
    assert alerts(claims={"sub": "u", "cognito:groups": "[not-inspectors]"})[0] == 403
