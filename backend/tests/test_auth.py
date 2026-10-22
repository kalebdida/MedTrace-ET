import pytest

import app
from medtrace.config import Settings
from tests.conftest import ADAMA, GTIN, call, claims_for, http_event, pharma_barcode, rest_event

SCAN = {"barcode": pharma_barcode(), "location": ADAMA}


def stored_item(aws, seq=1):
    return aws["table"].get_item(Key={"pk": f"SGTIN#{GTIN}#SN0001", "sk": str(seq).zfill(10)})["Item"]


def test_scan_requires_sign_in(aws):
    status, body = call(http_event("POST", "/scan", SCAN))
    assert status == 401
    assert body == {"error": "Sign-in required"}
    assert aws["table"].scan()["Count"] == 0


def test_history_requires_sign_in(aws):
    assert call(http_event("GET", "/history", query={"gtin": GTIN, "serial": "SN0001"}))[0] == 401


def test_parse_and_health_stay_public(aws):
    assert call(http_event("POST", "/parse", {"barcode": pharma_barcode()}))[0] == 200
    assert call(http_event("GET", "/health"))[0] == 200


def test_site_comes_from_the_token(aws):
    status, body = call(http_event("POST", "/scan", SCAN, claims=claims_for("user-7", "PH-ADAMA-001")))
    assert status == 200
    assert body["site_id"] == "PH-ADAMA-001"
    item = stored_item(aws)
    assert (item["site_id"], item["site_source"], item["actor"]) == ("PH-ADAMA-001", "token", "user-7")


def test_body_may_repeat_the_token_site(aws):
    body = {**SCAN, "site_id": "PH-ADAMA-001"}
    assert call(http_event("POST", "/scan", body, claims=claims_for("u", "PH-ADAMA-001")))[0] == 200


def test_body_cannot_claim_another_site(aws):
    body = {**SCAN, "site_id": "PH-DESSIE-007"}
    status, resp = call(http_event("POST", "/scan", body, claims=claims_for("u", "PH-ADAMA-001")))
    assert status == 403
    assert "does not match" in resp["error"]
    assert aws["table"].scan()["Count"] == 0


def test_account_without_site_reports_site_from_body(aws):
    # e.g. an EFDA field inspector who is not attached to one pharmacy
    body = {**SCAN, "site_id": "FIELD-CHECK-12"}
    call(http_event("POST", "/scan", body, claims=claims_for("inspector-3")))
    item = stored_item(aws)
    assert (item["site_id"], item["site_source"], item["actor"]) == ("FIELD-CHECK-12", "client", "inspector-3")


def test_malformed_site_claim_is_rejected(aws):
    claims = {"sub": "u", "custom:site_id": "bad site!"}
    assert call(http_event("POST", "/scan", SCAN, claims=claims))[0] == 403


def test_rest_api_cognito_authorizer_claims(aws):
    status, body = call(rest_event("POST", "/scan", SCAN, claims=claims_for("user-9", "PH-ADAMA-001")))
    assert status == 200
    assert body["site_id"] == "PH-ADAMA-001"


def test_custom_site_claim_name(aws, monkeypatch):
    monkeypatch.setenv("SITE_ID_CLAIM", "custom:pharmacy")
    monkeypatch.setattr(app, "_services", None)
    claims = {"sub": "u", "custom:pharmacy": "PH-ADAMA-001"}
    assert call(http_event("POST", "/scan", SCAN, claims=claims))[1]["site_id"] == "PH-ADAMA-001"


def test_auth_can_be_disabled_for_local_demos(aws, monkeypatch):
    monkeypatch.setenv("REQUIRE_AUTH", "false")
    monkeypatch.setattr(app, "_services", None)
    status, _ = call(http_event("POST", "/scan", {**SCAN, "site_id": "PH-ADAMA-001"}))
    assert status == 200
    item = stored_item(aws)
    assert item["site_source"] == "client"
    assert "actor" not in item


@pytest.mark.parametrize("raw, expected", [("true", True), ("FALSE", False), ("0", False), ("yes", True), ("", True)])
def test_require_auth_flag_parsing(raw, expected):
    assert Settings.from_env({"REQUIRE_AUTH": raw}).require_auth is expected


def test_require_auth_rejects_garbage():
    with pytest.raises(ValueError, match="REQUIRE_AUTH"):
        Settings.from_env({"REQUIRE_AUTH": "maybe"})
