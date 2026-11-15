"""Merging a duplicate child card into the one that stays (DATA_MODEL.md §4,
"Merging duplicate children"): a family that signed the same child up twice
(two cards, two histories). Only the organisation, from the Privacy page,
and only between children that share a guardian, so a card never moves to
another family. Everything the duplicate holds moves to the card that stays
(events.merge); the duplicate row is then deleted."""

from dataclasses import dataclass

from django.db import transaction
from django.db.models import F
from django.utils.translation import gettext as _

from accounts.models import GuardianInvitation, Guardianship, Ninja
from events import merge as events_merge

# What a card that stays takes over when its own is blank.
FILLED_WHEN_BLANK = ("family_name", "date_of_birth", "home_dojo", "photo", "allergies_notes")


class MergeError(Exception):
    """A merge that can't happen, with a message for the organisation."""


@dataclass
class Pair:
    first: Ninja
    second: Ninja


def candidates(limit: int = 50) -> list[Pair]:
    """Children with the same name (and family name) and a guardian in
    common: likely the same child signed up twice."""
    firsts = (
        Ninja.objects.filter(
            guardianships__guardian__guardianships__ninja_id__gt=F("id"),
            guardianships__guardian__guardianships__ninja__name__iexact=F("name"),
            guardianships__guardian__guardianships__ninja__family_name__iexact=F("family_name"),
        )
        .distinct()
        .order_by("id")[:limit]
    )
    pairs = []
    for first in firsts:
        for second in (
            Ninja.objects.filter(
                guardianships__guardian__guardianships__ninja=first,
                name__iexact=first.name,
                family_name__iexact=first.family_name,
                id__gt=first.id,
            )
            .distinct()
            .order_by("id")
        ):
            pairs.append(Pair(first, second))
    return pairs[:limit]


def problems(keep: Ninja, duplicate: Ninja) -> str | None:
    """Why `duplicate` can't be merged into `keep`, or None."""
    if keep.pk == duplicate.pk:
        return _("Pick two different children.")
    if duplicate.account_id:
        return _("%(name)s has a login of their own: merge into that card instead, or remove the login first.") % {
            "name": duplicate.full_name
        }
    shared = set(Guardianship.objects.filter(ninja=keep).values_list("guardian_id", flat=True)) & set(
        Guardianship.objects.filter(ninja=duplicate).values_list("guardian_id", flat=True)
    )
    if not shared:
        return _("The two children have no guardian in common: they aren't merged across families.")
    return None


def merge_children(keep: Ninja, duplicate: Ninja) -> None:
    """Move everything of `duplicate` onto `keep`, then delete `duplicate`.
    Raises MergeError. One transaction: all or nothing."""
    with transaction.atomic():
        pair = {n.pk: n for n in Ninja.objects.select_for_update().filter(pk__in=[keep.pk, duplicate.pk])}
        if len(pair) != 2:
            raise MergeError(_("One of the two children doesn't exist any more."))
        keep, duplicate = pair[keep.pk], pair[duplicate.pk]
        if message := problems(keep, duplicate):
            raise MergeError(message)

        events_merge.move_history(duplicate, keep)

        for field in FILLED_WHEN_BLANK:
            if not getattr(keep, field) and getattr(duplicate, field):
                setattr(keep, field, getattr(duplicate, field))
        if keep.gender == Ninja.UNSPECIFIED and duplicate.gender != Ninja.UNSPECIFIED:
            keep.gender = duplicate.gender
        dates = [d for d in (keep.member_since, duplicate.member_since) if d]
        keep.member_since = min(dates) if dates else None
        keep.save()

        # Everyone who was a guardian of either card is one of the card that stays.
        have = set(Guardianship.objects.filter(ninja=keep).values_list("guardian_id", flat=True))
        for guardianship in Guardianship.objects.filter(ninja=duplicate):
            if guardianship.guardian_id not in have:
                guardianship.ninja = keep
                guardianship.save(update_fields=["ninja"])
        GuardianInvitation.objects.filter(ninja=duplicate).delete()
        Guardianship.objects.filter(ninja=duplicate).delete()
        duplicate.delete()
