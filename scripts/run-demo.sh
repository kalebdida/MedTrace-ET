#!/usr/bin/env bash
set -euo pipefail
: "${API_URL:?}" "${SUPABASE_URL:?}" "${SUPABASE_ANON_KEY:?}" "${ADAMA_PASSWORD:?}" "${DESSIE_PASSWORD:?}"
root=$(cd "$(dirname "$0")/.." && pwd)
python3 - "$root" <<'PY'
import os,sys,json,uuid
from pathlib import Path
from datetime import datetime,timedelta,timezone
import httpx
root=Path(sys.argv[1]);serial=uuid.uuid4().hex[:20];now=datetime.now(timezone.utc);tokens={};results={}
with httpx.Client(timeout=30) as c:
 for city,minutes,name in [('ADAMA',50,'scan-adama'),('DESSIE',0,'scan-dessie-clone')]:
  login=c.post(os.environ['SUPABASE_URL'].rstrip('/')+'/auth/v1/token?grant_type=password',headers={'apikey':os.environ['SUPABASE_ANON_KEY']},json={'email':os.environ.get(city+'_EMAIL') or f'{city.lower()}@medtrace.demo','password':os.environ[city+'_PASSWORD']});login.raise_for_status();tokens[city]=login.json()['access_token']
  body=json.loads(json.loads((root/'backend/events'/f'{name}.json').read_text())['body']);body['barcode']=body['barcode'].replace('DEMO0001',serial);body['scanned_at']=(now-timedelta(minutes=minutes)).isoformat()
  response=c.post(os.environ['API_URL'].rstrip('/')+'/scan',headers={'Authorization':'Bearer '+tokens[city]},json=body);response.raise_for_status();result=response.json();results[city]=result;print(city,json.dumps({k:result[k] for k in ['verdict','flags','alert_sent']}))
 assert results['ADAMA']['verdict']=='PASS',results['ADAMA']
 assert results['DESSIE']['verdict']=='FAIL' and 'IMPOSSIBLE_TRAVEL' in [f['code'] for f in results['DESSIE']['flags']],results['DESSIE']
 history=c.get(os.environ['API_URL'].rstrip('/')+'/history',params={'gtin':'09506000134352','serial':serial},headers={'Authorization':'Bearer '+tokens['ADAMA']});history.raise_for_status();print('chain.valid:',history.json()['chain']['valid']);assert history.json()['chain']['valid']
PY
