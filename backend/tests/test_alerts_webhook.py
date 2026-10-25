import httpx
from medtrace.alerts_webhook import AlertPublisher


def test_webhooks(monkeypatch):
    record = {"pk": "x", "seq": 1, "record_hash": "hash"}
    monkeypatch.setattr(
        httpx,
        "post",
        lambda *a, **k: httpx.Response(
            204, request=httpx.Request("POST", "https://example.com")
        ),
    )
    assert AlertPublisher("https://example.com").publish_clone_alert(record, [])

    def fail(*a, **k):
        raise httpx.ConnectError("offline")

    monkeypatch.setattr(httpx, "post", fail)
    assert not AlertPublisher(ntfy="https://example.com").publish_clone_alert(
        record, []
    )
