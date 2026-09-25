"""A ninja's home dojo (`Ninja.home_dojo`): the dojo the family belongs to.

Hybrid assignment (DATA_MODEL.md §18):

- a child without one gets it at their first sign-up, from that session's
  dojo (`assign_on_signup`); an organisation dojo (Coolest Projects,
  CoderDojo Girlz) never becomes a home dojo;
- the guardian can change it (or clear it) on the child's page
  (`set_home_dojo`), to any public dojo;
- after that nothing moves it automatically: signing up somewhere else
  keeps the home dojo the family chose.

`member_since` is the day the child got their current home dojo.
The dojo team only reads it (the Members page); it never sets it.
"""

from django.db.models import Count
from django.utils import timezone

from dojos.models import Dojo


def home_dojo_choices():
    """The dojos a guardian can pick: the public ones."""
    return Dojo.objects.public().order_by("name")


def assign_on_signup(ninja, dojo):
    """Give `ninja` `dojo` as home dojo if they have none yet. Returns
    whether it was set."""
    if ninja.home_dojo_id is not None or dojo.kind != Dojo.DOJO:
        return False
    ninja.home_dojo = dojo
    ninja.member_since = timezone.localdate()
    ninja.save(update_fields=["home_dojo", "member_since"])
    return True


def set_home_dojo(ninja, dojo):
    """The guardian's choice (a public dojo, or None to clear it). Changing
    it restarts `member_since`; picking the same dojo changes nothing.
    Doesn't save: the caller saves the child together with the rest of
    the form."""
    if (dojo.pk if dojo else None) == ninja.home_dojo_id:
        return
    ninja.home_dojo = dojo
    ninja.member_since = timezone.localdate() if dojo else None


def backfill(ninjas=None):
    """For children without a home dojo: the regular dojo they came to most
    (marked present, else any confirmed place), first visit there as
    `member_since`. For data from before home dojos were assigned; returns
    how many were set."""
    from accounts.models import Ninja
    from events.models import Registration

    ninjas = Ninja.objects.filter(home_dojo=None) if ninjas is None else ninjas.filter(home_dojo=None)
    updated = 0
    for ninja in ninjas:
        places = Registration.objects.filter(ninja=ninja, waiting_list=False, event__dojo__kind=Dojo.DOJO)
        attended = places.filter(attended=True)
        source = attended if attended.exists() else places
        busiest = source.values("event__dojo").annotate(n=Count("id")).order_by("-n", "event__dojo").first()
        if busiest is None:
            continue
        dojo_id = busiest["event__dojo"]
        first = source.filter(event__dojo_id=dojo_id).order_by("event__start_time").first()
        ninja.home_dojo_id = dojo_id
        ninja.member_since = timezone.localdate(first.event.start_time)
        ninja.save(update_fields=["home_dojo", "member_since"])
        updated += 1
    return updated
