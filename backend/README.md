# MedTrace-ET Backend

Serverless Python core of MedTrace-ET. A single AWS Lambda function (container image) behind API Gateway that:

1. **Parses and validates GS1 DataMatrix codes**: splits the raw scanner string into structured JSON (GTIN, serial, batch, expiry, SSCC, …) and checks every element against the GS1 rules.
2. **Detects cloned barcodes**: compares each scan with earlier scans of the same serial. It flags *impossible travel* (the same serial in two cities further apart than any vehicle could cover in the time between scans) and *resurrected packs* (a serial that turns up again after it was dispensed).
3. **Keeps an immutable audit log** in DynamoDB. Each pack has an append-only, SHA-256 hash-chained record of every scan, so any edit or deletion is detectable.
4. **Raises Amazon SNS alerts** when a cloned barcode is intercepted.
5. **Publishes CloudWatch metrics** (Embedded Metric Format) for the operations and EFDA dashboards.

```
backend/
├── app.py                 Lambda handler: routing, request validation, scan orchestration
├── medtrace/
│   ├── gs1.py             GS1 element-string parser and validator
│   ├── velocity.py        Haversine travel-velocity and dispense-state clone detection
│   ├── audit.py           Append-only, hash-chained DynamoDB audit log
│   ├── alerts.py          SNS clone alerts (JSON for machines, plain text for email)
│   ├── metrics.py         CloudWatch EMF metrics
│   ├── flags.py           Risk flags -> PASS / WARN / FAIL verdict
│   ├── config.py          Environment-variable settings
│   └── jsonutil.py        Decimal/date JSON encoding
├── tests/                 pytest suite (DynamoDB/SNS mocked with moto)
├── events/                Sample API Gateway events (demo, sam local, Lambda console)
├── Dockerfile             Lambda container image
├── requirements.txt       Runtime dependencies
└── requirements-dev.txt   Test dependencies
```

The modules under `medtrace/` other than `audit.py` and `alerts.py` are pure Python with no AWS calls, so they can be unit-tested and reused (for example by the ML pipeline).

---

## API

All routes use Lambda proxy integration. API Gateway **HTTP APIs (payload 2.0)** and **REST APIs (payload 1.0)** are both supported, as are named stages (`/prod/scan`) and base64-encoded bodies. Responses are JSON and carry CORS headers.

| Method | Path       | Purpose |
|--------|------------|---------|
| GET    | `/health`  | Liveness probe; reports whether the table and topic are configured |
| POST   | `/parse`   | Parse and validate a barcode. Stateless; writes nothing |
| POST   | `/scan`    | Full verification: parse → clone check → audit log → alert |
| GET    | `/history` | Audit trail for one pack, with hash-chain verification |

### `POST /scan`

```json
{
  "barcode": "]d201095060001343521730123110BATCH42\u001d21DEMO0001",
  "event_type": "verify",
  "site_id": "PH-DESSIE-007",
  "device_id": "android-demo-2",
  "scanned_at": "2026-10-20T09:50:00+03:00",
  "location": { "lat": 11.13, "lon": 39.6333, "accuracy_m": 30 }
}
```

| Field | Required | Notes |
|-------|----------|-------|
| `barcode` | yes | Raw text decoded from the DataMatrix, ≤ 512 chars. **Keep the GS (`\u001d`) separators.** `<GS>`, `{GS}`, `[GS]`, `\x1d` and `␝` are also accepted. A `]d2` symbology prefix and the bracketed `(01)…(21)…` form are both fine. |
| `event_type` | no | `verify` (default), `receive`, `ship` or `dispense`. Stored with its EPCIS business step (`inspecting`, `receiving`, `shipping`, `dispensing`). |
| `location` | no, but needed for travel checks | `lat`/`lon` in degrees; `accuracy_m` is the GPS accuracy radius reported by the phone. |
| `site_id`, `device_id` | no | 1–64 chars of `A-Za-z0-9._:@/-`. |
| `scanned_at` | no | ISO-8601 **with timezone offset**. Defaults to server time. Lets an offline phone upload queued scans later. If the device clock is more than 5 min ahead, server time is used and a `CLOCK_SKEW` info flag is added. |

Response (abridged, from `events/scan-dessie-clone.json` after `events/scan-adama.json`):

```json
{
  "event_id": "d8648d6b-…",
  "verdict": "FAIL",
  "clone_suspected": true,
  "flags": [{
    "code": "IMPOSSIBLE_TRAVEL",
    "severity": "critical",
    "message": "This serial was also scanned 291 km away at site PH-ADAMA-001, 50 min apart. Travelling that far that fast (349 km/h, limit 120 km/h) is impossible, so the barcode has been cloned.",
    "clone_indicator": true,
    "details": { "distance_km": 290.73, "hours": 0.8333, "speed_kmh": 348.8, "prior_site_id": "PH-ADAMA-001", "…": "…" }
  }],
  "product": { "valid": true, "gtin": "09506000134352", "serial": "DEMO0001", "batch": "BATCH42", "expiry": "2030-12-31", "…": "same shape as /parse" },
  "travel": {
    "legs": [{ "prior_site_id": "PH-ADAMA-001", "distance_km": 290.73, "speed_kmh": 348.8, "impossible": true, "…": "…" }],
    "features": { "prior_scans": 1, "distinct_sites": 2, "prior_dispenses": 0, "hours_since_nearest_scan": 0.8333,
                  "max_distance_km": 290.73, "max_speed_kmh": 348.8, "impossible_legs": 1 }
  },
  "audit": { "pk": "SGTIN#09506000134352#DEMO0001", "seq": 2, "prev_hash": "517e8e9d…", "record_hash": "5dd331bc…" },
  "alert_sent": true
}
```

A scan whose verdict is FAIL still returns **HTTP 200**: the request succeeded and the verdict is the answer. 4xx means a malformed request, 503 means the backend isn't configured, and 500 is an unexpected error (logged with the request id; no internals are leaked).

### `POST /parse`

`{"barcode": "..."}` → structured JSON:

```json
{
  "valid": true,
  "symbology": "GS1 DataMatrix",
  "input_format": "element_string",
  "identifier_type": "trade_item",
  "gtin": "09506000134352", "serial": "DEMO0001", "batch": "BATCH42", "expiry": "2030-12-31", "sscc": null,
  "expired": false, "days_to_expiry": 1531,
  "serialization_complete": true, "missing_elements": [],
  "digital_link": "https://id.gs1.org/01/09506000134352/10/BATCH42/21/DEMO0001?17=301231",
  "elements": [
    { "ai": "01", "key": "gtin",   "title": "GTIN",             "value": "09506000134352" },
    { "ai": "17", "key": "expiry", "title": "USE BY OR EXPIRY", "value": "301231", "iso": "2030-12-31" },
    { "ai": "10", "key": "batch",  "title": "BATCH/LOT",        "value": "BATCH42" },
    { "ai": "21", "key": "serial", "title": "SERIAL",           "value": "DEMO0001" }
  ],
  "errors": [],
  "warnings": []
}
```

Errors and warnings carry a machine-readable `code` and a human-readable `message`, e.g. `{"code": "BAD_CHECK_DIGIT", "message": "GTIN (01) check digit is 3, expected 2.", "ai": "01"}`.

### `GET /history?gtin=…&serial=…` or `?sscc=…`

Returns every stored scan of the pack, oldest first (up to 500), and the result of re-verifying the hash chain:

```json
{ "identity": "SGTIN#09506000134352#DEMO0001", "scan_count": 2, "truncated": false,
  "chain": { "valid": true, "length": 2, "head_hash": "5dd331bc…" },
  "events": [ { "seq": 1, "site_id": "PH-ADAMA-001", "…": "…" }, { "seq": 2, "…": "…" } ] }
```

If a record was altered: `"chain": {"valid": false, "broken_at_seq": 1, "reason": "record_modified"}`. If one was deleted: `"reason": "missing_or_reordered_record"`.

---

## How the checks work

### GS1 parsing (`medtrace/gs1.py`)

- Strips AIM symbology identifiers (`]d2`, `]Q3`, `]C1`, `]e0`; `]d1` adds a "not GS1" warning) and normalises textual GS stand-ins to ASCII 29.
- Walks the element string AI by AI. The AI table is prefix-free (a test enforces this), so 2-, 3- and 4-digit AIs are matched unambiguously. Fixed-length AIs (`00`, `01`, `17`, …) consume exactly their length; variable-length AIs (`10`, `21`, …) run to the next GS or the end.
- Per element: exact length or maximum length, numeric vs. GS1 character set 82, **mod-10 check digit** for GTIN/SSCC, and real calendar dates for YYMMDD. `DD = 00` means the last day of the month, and the century follows the GS1 sliding window (−49/+50 years).
- Across elements: conflicting duplicate AIs, `01` together with `02`, and serial, batch or dates without a GTIN.
- Pharma completeness: `serialization_complete` requires GTIN (01), serial (21), batch (10) and expiry (17). If those are missing and no GS separators arrived, a `SEPARATOR_POSSIBLY_MISSING` warning suggests that the scanner stripped them.
- Supported AIs: 00, 01, 02, 10, 11, 13, 15, 16, 17, 20, 21, 22, 240, 241, 30, 37, 400, 710–715 (national healthcare reimbursement numbers), 7003, 90–99. An unsupported AI stops parsing with `UNKNOWN_AI`, because its length is unknown.

### Clone detection (`medtrace/velocity.py`)

A pack is identified by `GTIN + serial` (serials are only unique within a GTIN) or by its SSCC. For every new scan, the last `HISTORY_LIMIT` scans of that identity are loaded, and each earlier scan that has a location forms a **travel leg**:

```
distance  = haversine(current, prior)                       # great-circle km
effective = max(0, distance − (accuracy_current + accuracy_prior))   # GPS slack
hours     = max(|t_current − t_prior|, 1 s)
speed     = effective / hours
impossible = effective ≥ MIN_TRAVEL_DISTANCE_KM  and  speed > MAX_PLAUSIBLE_SPEED_KMH
```

- **120 km/h on straight-line distance** is the default limit. Roads are longer than great circles, so this already corresponds to faster-than-highway road travel. A legitimate Addis → Dessie delivery takes hours and passes; Adama → Dessie (291 km) in 50 min does not.
- Subtracting the reported GPS accuracy and ignoring hops under 2 km keeps poor fixes from generating alerts.
- The absolute time gap is used, so scans uploaded late from offline phones are compared correctly.

| Flag | Severity | Clone? | Raised when |
|------|----------|--------|-------------|
| `IMPOSSIBLE_TRAVEL` | critical | ✔ | Any leg is impossible (the worst leg is reported) |
| `ALREADY_DISPENSED` | critical | ✔ | A `dispense` arrives for a pack that was already dispensed |
| `DISPENSED_PACK_RESURFACED` | critical | ✔ | A dispensed pack is scanned at a different site or > 2 km away |
| `PREVIOUSLY_DISPENSED` | warning | | Re-scan after dispensing, at the same site |
| `INVALID_BARCODE` | critical | | GS1 validation failed |
| `EXPIRED` | critical | | Expiry date has passed (Ethiopian local date) |
| `NEAR_EXPIRY` | warning | | Expires within `NEAR_EXPIRY_DAYS` |
| `INCOMPLETE_SERIALIZATION` | warning | | GTIN present but serial, batch or expiry missing |
| `NO_PRODUCT_IDENTIFIER` | warning | | Valid GS1 data but neither GTIN nor SSCC |
| `CLOCK_SKEW` | info | | Device clock was ahead; server time used |

Verdict: any critical → **FAIL**, else any warning → **WARN**, else **PASS**. Any clone flag → SNS alert.

`travel.features` is a fixed numeric summary of the serial's movement (`prior_scans`, `distinct_sites`, `prior_dispenses`, `hours_since_nearest_scan`, `max_distance_km`, `max_speed_kmh`, `impossible_legs`). It is stored on every audit record and is the intended input for the Isolation Forest routing-anomaly model.

### Immutable audit log (`medtrace/audit.py`)

Each scan becomes one DynamoDB item, including scans that fail validation, which go under `UNIDENTIFIED#<date>`:

| Attribute | Example |
|-----------|---------|
| `pk` | `SGTIN#09506000134352#DEMO0001`, `SSCC#…` or `UNIDENTIFIED#2026-10-22` |
| `sk` | `0000000002` (position in this pack's chain) |
| `seq`, `prev_hash`, `record_hash` | chain linkage; `record_hash = SHA-256(canonical JSON of all other attributes)` |
| scan data | `event_id`, `received_at`, `scanned_at`, `event_type`, `biz_step`, `site_id`, `device_id`, `location`, `barcode_raw`, `gtin`, `serial`, `batch`, `expiry`, `sscc` |
| outcome | `verdict`, `clone_suspected`, `flags`, `travel_features` |

Immutability is enforced in layers:

1. **Code**: `PutItem` with `attribute_not_exists(pk)`. The code never updates or deletes.
2. **IAM**: the function role gets only `PutItem` and `Query` (policy below), so it *cannot* modify history.
3. **Tamper evidence**: every record hashes its predecessor. `GET /history` recomputes the chain, and an edited or deleted record is reported with its sequence number. Each new `record_hash` is also written to CloudWatch Logs, giving an independent copy.
4. **Concurrency**: the chain position is the sort key, so two simultaneous scans of the same serial (a clone being used in two cities at once) race for the same key. The loser gets `ChainConflict`, re-reads the history (which now includes the winner) and re-runs clone detection. Both cannot pass unseen.

---

## Infrastructure contract (for IaC / CI-CD)

### Lambda

- Package type: **Image**, built from `backend/Dockerfile` (base `public.ecr.aws/lambda/python:3.13`, handler `app.lambda_handler`).
- Suggested: 256 MB memory, 10 s timeout. A `/scan` normally makes 1 DynamoDB Query, 1 PutItem and at most 1 SNS Publish (plus one more Query/PutItem pair per retry when two scans of the same pack collide).

| Environment variable | Required | Default | Meaning |
|----------------------|----------|---------|---------|
| `SCAN_TABLE_NAME` | for `/scan`, `/history` | – | DynamoDB audit table |
| `ALERT_TOPIC_ARN` | no | – | SNS topic for clone alerts (alerts are skipped and logged if unset) |
| `MAX_PLAUSIBLE_SPEED_KMH` | no | `120` | Straight-line speed above which travel is impossible |
| `MIN_TRAVEL_DISTANCE_KM` | no | `2` | Hops shorter than this (after GPS slack) never trigger |
| `HISTORY_LIMIT` | no | `25` | Earlier scans compared per new scan |
| `NEAR_EXPIRY_DAYS` | no | `30` | Window for the `NEAR_EXPIRY` warning |
| `METRICS_NAMESPACE` | no | `MedTraceET` | CloudWatch namespace |
| `CORS_ALLOW_ORIGIN` | no | `*` | Value for `Access-Control-Allow-Origin` |
| `LOG_LEVEL` | no | `INFO` | Python log level |

No credentials are read from the environment; boto3 uses the Lambda execution role.

### DynamoDB table

- Partition key `pk` (String), sort key `sk` (String). No GSIs, no TTL (audit records are permanent).
- Provisioned 5 RCU / 5 WCU stays inside the always-free tier (25/25); on-demand also works and costs cents at hackathon volume.
- Recommended: `DeletionProtectionEnabled: true`. Point-in-time recovery is optional (small storage cost).

### SNS topic

Any topic. The handler publishes with `MessageStructure=json`: email subscribers get a readable plain-text report, while SQS, Lambda and HTTPS subscribers get the JSON payload. Message attributes `alert_type=CLONED_BARCODE` and `severity=critical` allow subscription filter policies.

### Least-privilege IAM policy for the function role

Attach this together with `AWSLambdaBasicExecutionRole` (CloudWatch Logs). EMF metrics need no `cloudwatch:PutMetricData`.

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "AppendAndReadAuditLog",
      "Effect": "Allow",
      "Action": ["dynamodb:PutItem", "dynamodb:Query"],
      "Resource": "arn:aws:dynamodb:${Region}:${AccountId}:table/${ScanTableName}"
    },
    {
      "Sid": "PublishCloneAlerts",
      "Effect": "Allow",
      "Action": "sns:Publish",
      "Resource": "${AlertTopicArn}"
    }
  ]
}
```

Do **not** grant `UpdateItem`, `DeleteItem` or `BatchWriteItem`: their absence is what makes the log append-only.

### CloudWatch

Metrics in namespace `MedTraceET`, dimension `Service=MedTraceBackend`: `ScansProcessed`, `CloneAlerts`, `AlertFailures`, `InvalidBarcodes` (Count) and `ScanLatency` (Milliseconds). An alarm on `CloneAlerts ≥ 1` or `AlertFailures ≥ 1` is a natural fit.

The same log line carries `verdict`, `flag_codes`, `site_id`, `lat`, `lon`, `gtin`, `pk`, `seq` and `record_hash` for Logs Insights. Counterfeit hotspots:

```
fields site_id, lat, lon
| filter CloneAlerts = 1
| stats count(*) as clone_alerts by site_id, lat, lon
| sort clone_alerts desc
```

---

## Local development

```bash
cd backend
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt
python -m pytest            # DynamoDB and SNS are mocked with moto; no AWS account needed
```

Build and invoke the container locally (the base image includes the Lambda Runtime Interface Emulator):

```bash
docker build -t medtrace-backend backend/
docker run --rm -p 9000:8080 medtrace-backend
curl -s localhost:9000/2015-03-31/functions/function/invocations -d @backend/events/parse.json
```

`/parse` and `/health` need no AWS resources. To exercise `/scan` against a real dev table, add `-e SCAN_TABLE_NAME=… -e AWS_REGION=…` plus temporary credentials from your shell (`-e AWS_ACCESS_KEY_ID -e AWS_SECRET_ACCESS_KEY -e AWS_SESSION_TOKEN`; never commit them). Then replay `events/scan-adama.json` followed by `events/scan-dessie-clone.json` to see a clone intercepted, and `events/history.json` to see the verified chain.

---

## Known limitations

- **Stripped separators**: if a scanner drops the GS/FNC1 characters, two variable-length fields (batch, serial) merge and cannot be split reliably. The parser warns (`SEPARATOR_POSSIBLY_MISSING`), but the mobile app must forward GS characters.
- **Bracketed input**: in the `(01)…` form, a literal `(NN)` inside a value would be read as a new AI.
- **AI coverage**: measurement AIs (31nn–36nn), GLN-based AIs and GS1 Digital Link URI *input* are not parsed yet.
- **First scan wins**: the first scan of a cloned serial is indistinguishable from the genuine one. Detection happens when the second copy is scanned, and the alert identifies both locations.
- **Location trust**: GPS comes from the client and could be spoofed by a compromised device. `site_id` should eventually be bound to the authenticated caller rather than supplied in the body.
- **History window**: clone checks compare against the last `HISTORY_LIMIT` (25) scans, and `/history` returns at most 500 records.
