"""Run locally with a service role key; never put that key in the Space."""

import os
import httpx

base = os.environ["SUPABASE_URL"].rstrip("/")
key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
with httpx.Client(
    base_url=base, headers={"apikey": key, "Authorization": "Bearer " + key}, timeout=20
) as client:
    for city, site in [("ADAMA", "PH-ADAMA-001"), ("DESSIE", "PH-DESSIE-007")]:
        response = client.post(
            "/auth/v1/admin/users",
            json={
                "email": f"pharmacist-{city.lower()}@medtrace.example",
                "password": os.environ[city + "_PASSWORD"],
                "email_confirm": True,
                "app_metadata": {"site_id": site},
            },
        )
        if response.is_error:
            raise RuntimeError(
                f"Could not create {city}: HTTP {response.status_code}; check whether user already exists in Auth Users"
            )
        print("Created", city)
