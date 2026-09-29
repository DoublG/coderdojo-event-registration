"""Fill the testers' authenticator (2FAuth, the devcontainer's `otp` service,
https://coolregistration.localhost/otp/) with the authenticator-app keys of
the accounts in the demo data, so a tester can log in to an account with
two-step login without an app on their own phone.

It syncs rather than adds: an account whose app changed gets its new key, one
that no longer has an app is removed. Only the entries it made itself (service
`SERVICE`) are touched, so anything a tester added by hand stays.
"""

from base64 import b32encode

import requests
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django_otp.plugins.otp_totp.models import TOTPDevice

# The name 2FAuth shows above each code, and how this command finds its own entries.
SERVICE = "CoderDojo (dev)"
# The shared user nginx signs everyone in as (Remote-User, .devcontainer/nginx/nginx.conf).
VAULT_USER = "testers"


class Command(BaseCommand):
    help = (
        "Put the authenticator-app key of every account with two-step login in the testers' authenticator "
        "(2FAuth at /otp/, OTP_VAULT_URL). Does nothing without OTP_VAULT_URL, i.e. outside the devcontainer."
    )

    def handle(self, *args, **options):
        base = settings.OTP_VAULT_URL
        if not base:
            self.stdout.write("OTP_VAULT_URL isn't set: no testers' authenticator to fill.")
            return
        session = requests.Session()
        session.headers.update({"Remote-User": VAULT_USER, "Accept": "application/json"})
        api = f"{base}/api/v1/twofaccounts"

        wanted = {}
        devices = TOTPDevice.objects.filter(confirmed=True, user__is_active=True).select_related("user")
        for device in devices.order_by("user__username"):
            wanted[device.user.username] = {
                "service": SERVICE,
                "account": device.user.username,
                "otp_type": "totp",
                "secret": b32encode(device.bin_key).decode("ascii"),
                "digits": device.digits,
                "algorithm": "sha1",
                "period": device.step,
            }

        try:
            response = session.get(api, params={"withSecret": 1}, timeout=10)
            response.raise_for_status()
        except requests.RequestException as error:
            raise CommandError(f"The testers' authenticator at {base} doesn't answer: {error}") from error

        added = removed = 0
        for entry in response.json():
            if entry.get("service") != SERVICE:
                continue
            want = wanted.get(entry["account"])
            if want and all(entry.get(k) == want[k] for k in ("secret", "digits", "period")):
                del wanted[entry["account"]]  # already there, unchanged
                continue
            session.delete(f"{api}/{entry['id']}", timeout=10).raise_for_status()
            removed += 1
        for want in wanted.values():
            session.post(api, json=want, timeout=10).raise_for_status()
            added += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Testers' authenticator: {devices.count()} account(s) with an app, {added} added, {removed} removed."
            )
        )
