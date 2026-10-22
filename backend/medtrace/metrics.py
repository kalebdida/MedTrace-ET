"""CloudWatch metrics via the Embedded Metric Format (EMF).

Printing an EMF document to stdout makes CloudWatch Logs extract the metrics
asynchronously: no PutMetricData calls, latency or extra IAM permissions.
Properties that are not metrics (site, verdict, coordinates) stay searchable
in CloudWatch Logs Insights, which is where the counterfeit-hotspot queries run.
"""

from __future__ import annotations

import json
import time

from .jsonutil import json_default

COUNT = "Count"
MILLISECONDS = "Milliseconds"


def emit(
    namespace: str,
    metrics: list[tuple[str, float, str]],
    dimensions: dict[str, str],
    properties: dict | None = None,
) -> None:
    document = {
        **(properties or {}),
        **dimensions,
        **{name: value for name, value, _ in metrics},
        "_aws": {
            "Timestamp": int(time.time() * 1000),
            "CloudWatchMetrics": [{
                "Namespace": namespace,
                "Dimensions": [sorted(dimensions)],
                "Metrics": [{"Name": name, "Unit": unit} for name, _, unit in metrics],
            }],
        },
    }
    print(json.dumps(document, default=json_default), flush=True)
