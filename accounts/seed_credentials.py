"""Shared helpers for seed commands that create login accounts.

Seed commands (seed_dojo_owners, seed_guardians, ...) each create real
User-subclass rows with a login password. Passwords must be randomly
generated (never a shared hardcoded demo password) and every created
username/email/password/role needs to end up somewhere a developer can
read for local testing, without ever going into a real deployment.
"""

import csv
import secrets
import string
from pathlib import Path

from django.conf import settings

CREDENTIALS_FILE = Path(settings.BASE_DIR) / "seed_credentials.csv"
FIELDNAMES = ["role", "username", "email", "password"]

_SYMBOLS = "!@#$%^&*-_=+"
_ALPHABET = string.ascii_letters + string.digits + _SYMBOLS


def generate_password(length=14):
    """Return a random password containing lower/upper/digit/symbol chars."""
    while True:
        password = "".join(secrets.choice(_ALPHABET) for _ in range(length))
        if (
            any(c.islower() for c in password)
            and any(c.isupper() for c in password)
            and any(c.isdigit() for c in password)
            and any(c in _SYMBOLS for c in password)
        ):
            return password


def write_credentials(role, rows):
    """Persist newly-created (username, email, password) rows for `role`.

    Replaces only this role's rows in the shared CSV so re-running one seed
    command doesn't clobber the credentials another seed command wrote.
    """
    existing = []
    if CREDENTIALS_FILE.exists():
        with open(CREDENTIALS_FILE, newline="") as f:
            existing = [row for row in csv.DictReader(f) if row["role"] != role]

    new_rows = [
        {"role": role, "username": username, "email": email, "password": password}
        for username, email, password in rows
    ]

    with open(CREDENTIALS_FILE, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(existing + new_rows)
