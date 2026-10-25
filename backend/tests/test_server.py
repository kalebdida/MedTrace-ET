import time
import jwt
from fastapi.testclient import TestClient
import server
from tests.conftest import pharma_barcode


def test_tokens_and_bridge(monkeypatch, aws):
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_JWT_SECRET", "test-secret")
    payload = {
        "sub": "user",
        "aud": "authenticated",
        "iss": "https://example.supabase.co/auth/v1",
        "exp": time.time() + 100,
        "app_metadata": {"site_id": "PH-ADAMA-001"},
        "user_metadata": {"site_id": "attacker"},
    }
    token = jwt.encode(payload, "test-secret", algorithm="HS256")
    assert server.claims(token)["custom:site_id"] == "PH-ADAMA-001"
    assert server.claims(jwt.encode(payload, "bad", algorithm="HS256")) is None
    assert (
        server.claims(
            jwt.encode({**payload, "exp": 0}, "test-secret", algorithm="HS256")
        )
        is None
    )
    client = TestClient(server.api)
    assert client.post("/scan", json={}).status_code == 401
    assert (
        client.post(
            "/scan", headers={"Authorization": "Bearer bad"}, json={}
        ).status_code
        == 401
    )
    response = client.post(
        "/scan",
        headers={"Authorization": "Bearer " + token},
        json={"barcode": pharma_barcode()},
    )
    assert response.status_code == 200 and response.json()["site_id"] == "PH-ADAMA-001"
    assert client.get("/metrics").json()["ScansProcessed"] >= 1
    assert client.get("/health").status_code == 200


def test_asymmetric_jwks_and_audience(monkeypatch):
    from cryptography.hazmat.primitives.asymmetric import rsa
    from types import SimpleNamespace

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setattr(
        server,
        "jwks",
        lambda url: SimpleNamespace(
            get_signing_key_from_jwt=lambda token: SimpleNamespace(key=key.public_key())
        ),
    )
    payload = {
        "sub": "user",
        "aud": "authenticated",
        "iss": "https://example.supabase.co/auth/v1",
        "exp": time.time() + 100,
        "user_metadata": {"site_id": "attacker"},
    }
    assert server.claims(jwt.encode(payload, key, algorithm="RS256")) == {"sub": "user"}
    assert (
        server.claims(jwt.encode({**payload, "aud": "wrong"}, key, algorithm="RS256"))
        is None
    )
