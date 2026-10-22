"""JSON helpers for values that come back from DynamoDB."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal


def json_default(value):
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")
