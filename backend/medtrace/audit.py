"""Append-only, hash-chained audit log of scans in DynamoDB.

Every scan of a pack is one item in that pack's partition:

    pk  = "SGTIN#<gtin>#<serial>" | "SSCC#<sscc>" | "UNIDENTIFIED#<yyyy-mm-dd>"
    sk  = zero-padded position in the pack's chain ("0000000001", ...)

Each item stores ``prev_hash`` (the previous item's ``record_hash``) and
``record_hash`` (SHA-256 over the item's canonical JSON), so editing or
deleting any record breaks the chain and shows up in ``verify_chain``.

Writes use ``attribute_not_exists`` and never overwrite. Because the sort key
is the chain position, two concurrent scans of the same serial race for the
same key: the loser gets ``ChainConflict``, re-reads the history (which now
includes the winner) and re-runs clone detection. Simultaneous scans of a
cloned code therefore cannot both pass unseen.

The function's IAM role should allow only PutItem and Query, so the
application has no way to modify or remove history.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping
from decimal import Decimal

from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError

GENESIS_HASH = "0" * 64
SEQ_WIDTH = 10


class ChainConflict(Exception):
    """Another writer appended to the same chain first."""


class AuditLog:
    def __init__(self, table):
        self._table = table

    def recent(self, pk: str, limit: int) -> list[dict]:
        """Newest-first records for one pack."""
        resp = self._table.query(
            KeyConditionExpression=Key("pk").eq(pk),
            ScanIndexForward=False,
            Limit=limit,
        )
        return resp.get("Items", [])

    def full_history(self, pk: str, max_items: int = 500) -> tuple[list[dict], bool]:
        """Oldest-first records for one pack, and whether the list was cut short."""
        items: list[dict] = []
        kwargs = {"KeyConditionExpression": Key("pk").eq(pk), "ScanIndexForward": True}
        while True:
            resp = self._table.query(**kwargs)
            items.extend(resp.get("Items", []))
            last_key = resp.get("LastEvaluatedKey")
            if not last_key or len(items) > max_items:
                break
            kwargs["ExclusiveStartKey"] = last_key
        truncated = len(items) > max_items or bool(last_key)
        return items[:max_items], truncated

    def append(self, pk: str, head: Mapping | None, fields: Mapping) -> dict:
        """Write the next record after ``head`` (the newest existing record, or None)."""
        seq = int(head["seq"]) + 1 if head else 1
        item = {
            **to_dynamo(dict(fields)),
            "pk": pk,
            "sk": str(seq).zfill(SEQ_WIDTH),
            "seq": seq,
            "prev_hash": head["record_hash"] if head else GENESIS_HASH,
        }
        item["record_hash"] = record_hash(item)
        try:
            self._table.put_item(Item=item, ConditionExpression="attribute_not_exists(pk)")
        except ClientError as err:
            if err.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
                raise ChainConflict(pk) from err
            raise
        return item


def record_hash(item: Mapping) -> str:
    body = {k: v for k, v in item.items() if k != "record_hash"}
    canonical = json.dumps(_canonical(body), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def verify_chain(items: list[Mapping]) -> dict:
    """Check an oldest-first chain that starts at the genesis record."""
    expected_prev, expected_seq = GENESIS_HASH, 1
    for item in items:
        seq = int(item.get("seq", -1))
        if seq != expected_seq or item.get("prev_hash") != expected_prev:
            return {"valid": False, "length": len(items), "broken_at_seq": expected_seq, "reason": "missing_or_reordered_record"}
        if record_hash(item) != item.get("record_hash"):
            return {"valid": False, "length": len(items), "broken_at_seq": seq, "reason": "record_modified"}
        expected_prev, expected_seq = item["record_hash"], seq + 1
    return {"valid": True, "length": len(items), "head_hash": expected_prev}


def to_dynamo(value):
    """Convert floats to Decimal recursively, as the DynamoDB resource API requires."""
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("DynamoDB cannot store NaN or infinite numbers")
        return Decimal(repr(value))
    if isinstance(value, Mapping):
        return {k: to_dynamo(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [to_dynamo(v) for v in value]
    return value


def _canonical(value):
    # Numbers must hash identically before writing (int/float/Decimal) and
    # after reading back (always Decimal, possibly re-normalised by DynamoDB).
    if value is None or isinstance(value, (bool, str)):
        return value
    if isinstance(value, (int, float, Decimal)):
        number = Decimal(str(value)).normalize()
        return int(number) if number == number.to_integral_value() else float(number)
    if isinstance(value, Mapping):
        return {str(k): _canonical(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_canonical(v) for v in value]
    raise TypeError(f"Unsupported type in audit record: {type(value).__name__}")
