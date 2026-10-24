#!/usr/bin/env bash
set -euo pipefail
: "${USER_POOL_ID:?}" "${USER_POOL_CLIENT_ID:?}" "${ADAMA_PASSWORD:?}" "${DESSIE_PASSWORD:?}"
# JSON on stdin keeps passwords out of process arguments and temporary files.
for city in ADAMA DESSIE; do
  username="pharmacist-${city,,}"
  if ! aws cognito-idp admin-get-user --user-pool-id "$USER_POOL_ID" --username "$username" >/dev/null 2>&1; then
    aws cognito-idp admin-create-user --user-pool-id "$USER_POOL_ID" --username "$username" --message-action SUPPRESS >/dev/null
  fi
  site=PH-ADAMA-001
  [[ $city == ADAMA ]] || site=PH-DESSIE-007
  aws cognito-idp admin-update-user-attributes --user-pool-id "$USER_POOL_ID" --username "$username" --user-attributes "Name=custom:site_id,Value=$site"
  export DEMO_CITY="$city"
  python3 - <<'PY' | aws cognito-idp admin-set-user-password --cli-input-json /dev/stdin
import os,json
city=os.environ['DEMO_CITY']
print(json.dumps(dict(UserPoolId=os.environ['USER_POOL_ID'],Username='pharmacist-'+city.lower(),Password=os.environ[city+'_PASSWORD'],Permanent=True)))
PY
done
cat <<'HELP'
Get each ID token with USER_PASSWORD_AUTH (never enable shell tracing):
python3 - <<'PY' | aws cognito-idp initiate-auth --cli-input-json /dev/stdin --query AuthenticationResult.IdToken --output text
import os,json
print(json.dumps(dict(ClientId=os.environ['USER_POOL_CLIENT_ID'],AuthFlow='USER_PASSWORD_AUTH',AuthParameters=dict(USERNAME='pharmacist-adama',PASSWORD=os.environ['ADAMA_PASSWORD']))))
PY
Repeat with pharmacist-dessie and DESSIE_PASSWORD. Export the tokens as ID_TOKEN and DESSIE_ID_TOKEN.
HELP
