"""Test helpers for building dojos and their teams (dojos.DojoMembership).
Used by the test modules of several apps; not imported by the site itself."""

from django.utils import timezone

from .models import Dojo, DojoMembership


def make_dojo(name="Ghent", champion=None, status=Dojo.ACTIVE, **fields):
    """A dojo that's `active` (public) unless told otherwise — the model
    default is draft, which hides the dojo and its events from the public
    site. With `champion`, that account becomes its active champion."""
    dojo = Dojo.objects.create(name=name, status=status, **fields)
    if champion is not None:
        add_member(dojo, champion, DojoMembership.CHAMPION)
    return dojo


def add_member(dojo, user, role=DojoMembership.MENTOR, status=DojoMembership.ACTIVE, **fields):
    joined_at = fields.pop("joined_at", timezone.now() if status == DojoMembership.ACTIVE else None)
    return DojoMembership.objects.create(dojo=dojo, user=user, role=role, status=status, joined_at=joined_at, **fields)


def _approved_account(kind, **fields):
    """An adult account approved the way the real flow leaves it: a
    validated, unexpired background check and an approved application."""
    from datetime import timedelta

    from accounts.models import User
    from applications.models import Application

    user = User.objects.create(
        background_check_status=User.CHECK_VALIDATED,
        background_check_expires_at=timezone.now() + timedelta(days=365),
        **fields,
    )
    Application.objects.create(account=user, kind=kind, status=Application.APPROVED)
    return user


def make_champion(**fields):
    """An approved champion account (may create dojos and run their own)."""
    from applications.models import Application

    return _approved_account(Application.CHAMPION, **fields)


def make_mentor(**fields):
    """An approved mentor account (may join, or be added to, dojo teams)."""
    from applications.models import Application

    return _approved_account(Application.MENTOR, **fields)
