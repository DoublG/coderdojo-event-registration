"""Shared helpers for seed commands that create login accounts.

Seed commands (seed_champions, seed_guardians, ...) each create real
User-subclass rows with a login password. Passwords must be randomly
generated (never a shared hardcoded demo password) and every created
username/email/password/role needs to end up somewhere a developer can
read for local testing, without ever going into a real deployment.

Every row also gets a `description`: what a tester can do with that
login (champion of which dojos, parent of which children, a child login
that's a youth mentor, ...), worked out from the database so it stays
true as later seeders add to the same account (`describe_account`).
`manage.py describe_seed_accounts` refreshes them all (start.sh runs it).
"""

import csv
import secrets
import string
from datetime import date
from pathlib import Path

from django.conf import settings

CREDENTIALS_FILE = Path(settings.BASE_DIR) / "seed_credentials.csv"
FIELDNAMES = ["role", "username", "email", "password", "description"]

# Seeded accounts use these domains (seeded child logins have no email).
SEED_EMAIL_DOMAINS = ("@coderdojo-demo.example", "@coderdojobelgium.example")

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


def read_credentials():
    if not CREDENTIALS_FILE.exists():
        return []
    with open(CREDENTIALS_FILE, newline="") as f:
        return list(csv.DictReader(f))


def _write(rows):
    with open(CREDENTIALS_FILE, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def write_credentials(role, rows):
    """Add (or update) the (username, email, password) rows of newly created
    `role` accounts. Merges by username: rerunning a seed command never
    drops the credentials an earlier run (or another command) wrote."""
    by_username = {row["username"]: row for row in read_credentials()}
    for username, email, password in rows:
        by_username[username] = {"role": role, "username": username, "email": email, "password": password}
    _write(describe_rows(list(by_username.values())))


def describe_rows(rows):
    from accounts.models import User

    users = {u.username: u for u in User.objects.filter(username__in=[r["username"] for r in rows])}
    for row in rows:
        user = users.get(row["username"])
        row["description"] = describe_account(user) if user else "Account no longer exists."
    return rows


def _names(items, limit=3):
    items = list(items)
    shown = ", ".join(items[:limit])
    return shown + (f" and {len(items) - limit} more" if len(items) > limit else "")


def _age(ninja):
    if not ninja.date_of_birth:
        return ""
    today = date.today()
    years = today.year - ninja.date_of_birth.year - ((today.month, today.day) < (ninja.date_of_birth.month, ninja.date_of_birth.day))
    return f" ({years})"


def describe_account(user):
    """What a tester can do with this login, in one line."""
    from accounts.models import Ninja
    from applications.models import Application
    from content.models import OrganisationTeamMember
    from dojos.models import Dojo, DojoMembership

    parts = []
    if user.is_superuser:
        parts.append("Superuser (Django admin)")
    for role in user.organisation_roles.all():
        parts.append("Organisation admin: /manage/ dashboard and Django admin" if role.role == role.ADMIN
                     else "Organisation board: read-only Django admin")
    listing = OrganisationTeamMember.objects.filter(account=user).first()
    if listing:
        parts.append(f"on the organisation's team page as {listing.position}")

    memberships = list(user.dojo_memberships.select_related("dojo").order_by("dojo__name"))

    def dojo_label(m):
        status = "" if m.dojo.status == Dojo.ACTIVE else f" [{m.dojo.get_status_display().lower()}]"
        languages = "/".join(code.split("-")[0].upper() for code in m.dojo.content_languages())
        return f"{m.dojo.name}{status} ({languages})"

    def with_status(role, status):
        return [dojo_label(m) for m in memberships if m.role == role and m.status == status]

    if champion := with_status(DojoMembership.CHAMPION, DojoMembership.ACTIVE):
        parts.append(f"Champion of {len(champion)} dojo{'s' if len(champion) > 1 else ''}: {_names(champion)}")
    if mentor := with_status(DojoMembership.MENTOR, DojoMembership.ACTIVE):
        parts.append(f"Mentor at {len(mentor)} dojo{'s' if len(mentor) > 1 else ''}: {_names(mentor)}")
    if youth := with_status(DojoMembership.YOUTH_MENTOR, DojoMembership.ACTIVE):
        parts.append(f"Youth mentor at {_names(youth)}")
    if requested := [dojo_label(m) for m in memberships if m.status == DojoMembership.REQUESTED]:
        parts.append(f"join request pending at {_names(requested)}")
    if former := [dojo_label(m) for m in memberships if m.status == DojoMembership.DORMANT]:
        parts.append(f"former team member at {_names(former)}")
    if any(m.status == DojoMembership.ACTIVE and m.role != DojoMembership.YOUTH_MENTOR for m in memberships):
        if not user.background_check_valid:
            parts.append("background check NOT valid, so no dojo dashboard access")

    for application in Application.objects.filter(account=user).select_related("dojo"):
        where = f" for {application.dojo.name}" if getattr(application, "dojo_id", None) else ""
        parts.append(f"{application.get_kind_display()} application {application.get_status_display().lower()}{where}")
    if user.background_check_status != user.CHECK_NOT_REQUESTED or user.applications.exists():
        if user.background_check_valid:
            parts.append(f"background check valid until {user.background_check_expires_at:%d/%m/%Y}")
        elif user.background_check_status == user.CHECK_SUBMITTED:
            parts.append("background check uploaded, awaiting review")
        elif user.background_check_can_upload:
            parts.append(f"background check {user.get_background_check_status_display().split(' —')[0].lower()}"
                         " (can upload from the account page)")

    if user.is_ninja:
        ninja = Ninja.objects.filter(account=user).prefetch_related("guardianships__guardian").select_related("home_dojo").first()
        if ninja:
            guardians = [g.guardian.username for g in ninja.guardianships.all()]
            parts.insert(0, f"Child login of {ninja.name}{_age(ninja)}"
                            f"{', home dojo ' + ninja.home_dojo.name if ninja.home_dojo else ''}"
                            f"; guardian: {_names(guardians)}; can sign up for sessions itself")
        if not user.email:
            parts.append("no email, so no mails")
    else:
        children = list(Ninja.objects.of_guardian(user).select_related("account", "home_dojo"))
        if children:
            described = [f"{c.name}{_age(c)}{' [own login]' if c.account_id and c.account.is_active else ''}" for c in children]
            parts.append(f"Parent of {len(children)} child{'ren' if len(children) > 1 else ''}: {_names(described, 4)}")
        if not parts:
            parts.append("Plain adult account (no children, no roles)")

    if not user.is_active:
        parts.append("DISABLED (can't log in)")
    if user.preferred_language:
        parts.append(f"mails in {user.get_preferred_language_display()}")
    return "; ".join(parts) + "."
