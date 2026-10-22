from decimal import Decimal

import pytest

from medtrace.audit import GENESIS_HASH, AuditLog, ChainConflict, record_hash, to_dynamo, verify_chain

PK = "SGTIN#09506000134352#SN1"


def test_hash_is_stable_across_number_representations():
    written = {"pk": "x", "lat": 9.0, "count": 3, "speed": 290.123456789, "ok": True, "none": None}
    read_back = {
        "pk": "x", "lat": Decimal("9"), "count": Decimal("3"),
        "speed": Decimal("290.123456789"), "ok": True, "none": None,
    }
    assert record_hash(written) == record_hash(to_dynamo(written)) == record_hash(read_back)


def test_hash_changes_with_content_and_ignores_own_field():
    item = {"pk": "x", "site_id": "PH-1"}
    assert record_hash(item) != record_hash({**item, "site_id": "PH-2"})
    assert record_hash(item) == record_hash({**item, "record_hash": "anything"})


def test_to_dynamo_rejects_non_finite_numbers():
    with pytest.raises(ValueError):
        to_dynamo({"speed": float("inf")})


def test_append_builds_a_verifiable_chain(aws):
    log = AuditLog(aws["table"])
    first = log.append(PK, None, {"event_id": "e1", "lat": 8.54})
    second = log.append(PK, first, {"event_id": "e2", "lat": 11.13})

    assert first["prev_hash"] == GENESIS_HASH
    assert second["prev_hash"] == first["record_hash"]
    assert [i["sk"] for i in log.recent(PK, 5)] == ["0000000002", "0000000001"]

    items, truncated = log.full_history(PK)
    assert not truncated
    assert verify_chain(items) == {"valid": True, "length": 2, "head_hash": second["record_hash"]}


def test_concurrent_append_on_same_head_conflicts(aws):
    log = AuditLog(aws["table"])
    head = log.append(PK, None, {"event_id": "e1"})
    log.append(PK, head, {"event_id": "e2"})
    with pytest.raises(ChainConflict):
        log.append(PK, head, {"event_id": "e3-racing"})


def test_modified_record_breaks_chain(aws):
    log = AuditLog(aws["table"])
    head = None
    for n in range(3):
        head = log.append(PK, head, {"event_id": f"e{n}", "site_id": "PH-1"})
    item = log.full_history(PK)[0][1]
    aws["table"].put_item(Item={**item, "site_id": "PH-FORGED"})

    result = verify_chain(log.full_history(PK)[0])
    assert result == {"valid": False, "length": 3, "broken_at_seq": 2, "reason": "record_modified"}


def test_deleted_record_breaks_chain(aws):
    log = AuditLog(aws["table"])
    head = None
    for n in range(3):
        head = log.append(PK, head, {"event_id": f"e{n}"})
    aws["table"].delete_item(Key={"pk": PK, "sk": "0000000002"})

    result = verify_chain(log.full_history(PK)[0])
    assert result["valid"] is False
    assert result["reason"] == "missing_or_reordered_record"
    assert result["broken_at_seq"] == 2


def test_full_history_reports_truncation(aws):
    log = AuditLog(aws["table"])
    head = None
    for n in range(4):
        head = log.append(PK, head, {"event_id": f"e{n}"})
    items, truncated = log.full_history(PK, max_items=3)
    assert truncated
    assert [int(i["seq"]) for i in items] == [1, 2, 3]
