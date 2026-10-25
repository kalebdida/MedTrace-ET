"""Best-effort alerts; failures never discard audit records."""

import httpx
from .alerts import _email_body


class AlertPublisher:
    def __init__(self, discord=None, ntfy=None):
        self.discord, self.ntfy = discord, ntfy

    def publish_clone_alert(self, record, flags):
        text = _email_body(
            {
                **record,
                "flags": [f.to_dict() for f in flags if f.clone_indicator],
                "audit": {k: record[k] for k in ("pk", "seq", "record_hash")},
            }
        )
        success = True
        for url, discord in [(self.discord, True), (self.ntfy, False)]:
            if not url:
                continue
            try:
                response = httpx.post(
                    url,
                    timeout=10,
                    **(
                        {"json": {"content": text[:2000]}}
                        if discord
                        else {"content": text.encode()}
                    ),
                )
                response.raise_for_status()
            except httpx.HTTPError:
                success = False
        return success
