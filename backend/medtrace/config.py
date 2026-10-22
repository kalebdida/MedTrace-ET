"""Runtime settings, read from Lambda environment variables."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    table_name: str | None = None
    alert_topic_arn: str | None = None
    max_speed_kmh: float = 120.0
    min_distance_km: float = 2.0
    history_limit: int = 25
    near_expiry_days: int = 30
    metrics_namespace: str = "MedTraceET"
    cors_allow_origin: str = "*"

    @classmethod
    def from_env(cls, env: Mapping[str, str] = os.environ) -> Settings:
        defaults = cls()
        return cls(
            table_name=env.get("SCAN_TABLE_NAME") or None,
            alert_topic_arn=env.get("ALERT_TOPIC_ARN") or None,
            max_speed_kmh=_number(env, "MAX_PLAUSIBLE_SPEED_KMH", defaults.max_speed_kmh, float),
            min_distance_km=_number(env, "MIN_TRAVEL_DISTANCE_KM", defaults.min_distance_km, float),
            history_limit=_number(env, "HISTORY_LIMIT", defaults.history_limit, int),
            near_expiry_days=_number(env, "NEAR_EXPIRY_DAYS", defaults.near_expiry_days, int),
            metrics_namespace=env.get("METRICS_NAMESPACE") or defaults.metrics_namespace,
            cors_allow_origin=env.get("CORS_ALLOW_ORIGIN") or defaults.cors_allow_origin,
        )


def _number(env: Mapping[str, str], name: str, default, kind):
    raw = env.get(name)
    if raw in (None, ""):
        return default
    try:
        value = kind(raw)
    except ValueError:
        raise ValueError(f"Environment variable {name} must be a {kind.__name__}, got {raw!r}") from None
    if value <= 0:
        raise ValueError(f"Environment variable {name} must be positive, got {raw!r}")
    return value
