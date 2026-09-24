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
