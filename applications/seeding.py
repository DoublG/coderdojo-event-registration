"""Seed-data helper: make an account an approved champion/mentor the way
the real flow would leave it — a validated background check on the account,
the matching BackgroundCheckHistory row, and an approved Application.
Used by the seed_* commands only, never by the site."""

import random
from datetime import timedelta

from django.utils import timezone

from accounts.models import User

from .models import BACKGROUND_CHECK_VALIDITY, Application, BackgroundCheckHistory


def approve_for_seeding(user, kind, rng=None, **application_fields):
    rng = rng or random.Random(user.pk)
    if not user.background_check_valid:
        reviewed_at = timezone.now() - timedelta(days=rng.randint(10, 300))
        user.background_check_status = User.CHECK_VALIDATED
        user.background_check_requested_at = reviewed_at - timedelta(days=14)
        user.background_check_submitted_at = reviewed_at - timedelta(days=3)
        user.background_check_reviewed_at = reviewed_at
        user.background_check_expires_at = reviewed_at + BACKGROUND_CHECK_VALIDITY
        user.save(update_fields=[
            "background_check_status", "background_check_requested_at", "background_check_submitted_at",
            "background_check_reviewed_at", "background_check_expires_at",
        ])
        BackgroundCheckHistory.objects.create(
            account=user, decision=BackgroundCheckHistory.VALIDATED, reviewed_at=reviewed_at,
            requested_at=user.background_check_requested_at, submitted_at=user.background_check_submitted_at,
            expires_at=user.background_check_expires_at, note="Seed data",
        )
    application, _ = Application.objects.get_or_create(
        account=user, kind=kind, status=Application.APPROVED,
        defaults={
            "decided_at": user.background_check_reviewed_at,
            "background_check_consent": True,
            "consent": kind == Application.CHAMPION,
            **application_fields,
        },
    )
    return application
