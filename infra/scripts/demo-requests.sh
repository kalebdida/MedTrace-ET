#!/usr/bin/env bash
set -euo pipefail
: "${API_URL:?}" "${ID_TOKEN:?Adama ID token}" "${DESSIE_ID_TOKEN:?Dessie ID token required by site binding}"
root=$(cd "$(dirname "$0")/../.." && pwd)
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
python3 - "$root" "$work" <<'PY'
import json,sys,uuid
from pathlib import Path
from datetime import datetime,timedelta,timezone
root,out=map(Path,sys.argv[1:]); serial=uuid.uuid4().hex[:20]; now=datetime.now(timezone.utc)
for name,minutes in [('scan-adama',50),('scan-dessie-clone',0)]:
 b=json.loads(json.loads((root/'backend/events'/f'{name}.json').read_text())['body'])
 b['barcode']=b['barcode'].replace('DEMO0001',serial)
 b['scanned_at']=(now-timedelta(minutes=minutes)).isoformat()
 (out/f'{name}.json').write_text(json.dumps(b))
(out/'serial').write_text(serial)
PY
request() {
 local token=$1; shift
 # Header through stdin avoids exposing JWTs in process arguments.
 printf 'Authorization: Bearer %s\n' "$token" | curl --silent --show-error --fail-with-body -H @- -H 'Content-Type: application/json' "$@"
}
request "$ID_TOKEN" --data-binary "@$work/scan-adama.json" "${API_URL%/}/scan" > "$work/first"
jq -e '.audit.seq == 1 and .clone_suspected == false' "$work/first"
request "$DESSIE_ID_TOKEN" --data-binary "@$work/scan-dessie-clone.json" "${API_URL%/}/scan" > "$work/second"
jq -e '.clone_suspected == true and any(.flags[]; .code == "IMPOSSIBLE_TRAVEL")' "$work/second"
request "$ID_TOKEN" "${API_URL%/}/history?gtin=09506000134352&serial=$(cat "$work/serial")" | jq -e '.scan_count == 2 and .chain.valid == true'
