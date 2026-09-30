"""Signing children up for a session and cancelling a place: the places, the
waiting list and its positions (CAPACITY.md, finding 1).

Both lock the session's row first (`SELECT ... FOR UPDATE`), so sign-ups
and cancellations for one session happen one at a time: two families
clicking at the same moment can't both take the last place, get the same
waiting-list position, or be promoted into the same freed place. Everything
they decide on (who's already signed up, how many places are taken, whether
registrations are still open) is read after taking the lock. Django runs
MySQL at READ COMMITTED, so those reads see what the transaction before
committed. Sessions don't wait on each other: the lock is per session."""

from django.db import transaction
from django.db.models import Max
from django.utils.translation import gettext as _

from accounts.home_dojo import assign_on_signup
from mailing.automated import booking_mail, waitlist_promoted_mail

from .models import Event, Registration, RegistrationCancellation


class RegistrationError(Exception):
    """A sign-up that can't happen, with a message for the family."""


def _lock(event_id):
    return Event.objects.select_for_update().get(pk=event_id)


def sign_up(event, children):
    """Sign `children` up for `event`, in order: a confirmed place while
    there are places, the waiting list after that. Children already signed
    up are skipped. Returns [{"child", "waiting_list", "registration"}] for
    the new ones; raises RegistrationError when registrations are closed or every
    child is already signed up. Their booking mail is queued in the same
    transaction: none for a sign-up that didn't happen."""
    with transaction.atomic():
        event = _lock(event.pk)
        if not event.registration_open:
            raise RegistrationError(_("Registrations for this session are closed."))
        signed_up = set(
            Registration.objects.filter(event=event, ninja__in=children).values_list("ninja_id", flat=True)
        )
        new_children = [child for child in children if child.id not in signed_up]
        if not new_children:
            raise RegistrationError(_("The child(ren) you selected are already signed up for this session."))

        position = Registration.objects.filter(event=event).aggregate(Max("position"))["position__max"] or 0
        confirmed = Registration.objects.filter(event=event, waiting_list=False).count()
        pathways = list(event.pathways.all())
        results = []
        for child in new_children:
            position += 1
            waiting_list = confirmed >= event.places
            registration = Registration.objects.create(
                event=event, ninja=child, waiting_list=waiting_list, position=position
            )
            # What the ninja works on starts as everything the session
            # covers; the dojo team narrows it on the attendance list.
            registration.pathways.set(pathways)
            # A child's first sign-up gives them their home dojo.
            assign_on_signup(child, event.dojo)
            if not waiting_list:
                confirmed += 1
            results.append({"child": child, "waiting_list": waiting_list, "registration": registration})
            booking_mail(registration)
        return results


def cancel(registration, cancelled_by):
    """Cancel `registration` (logged as a RegistrationCancellation). When it
    held a confirmed place and the session now has a place free, the child
    waiting longest gets it and their family is mailed. Returns the promoted
    registration, or None. A registration cancelled already (a second click)
    does nothing."""
    with transaction.atomic():
        event = _lock(registration.event_id)
        registration = Registration.objects.filter(pk=registration.pk).select_related("ninja").first()
        if registration is None:
            return None
        RegistrationCancellation.objects.create(
            ninja=registration.ninja,
            event=event,
            was_waitlisted=registration.waiting_list,
            signed_up_at=registration.created_at,
            cancelled_by=cancelled_by,
        )
        was_confirmed = not registration.waiting_list
        registration.delete()
        if not was_confirmed:
            return None
        # Only into a place that's really free: a session the team gave fewer
        # places after it filled up stays as it is.
        if Registration.objects.filter(event=event, waiting_list=False).count() >= event.places:
            return None
        promoted = Registration.objects.filter(event=event, waiting_list=True).order_by("position").first()
        if promoted is None:
            return None
        promoted.waiting_list = False
        promoted.save(update_fields=["waiting_list"])
        waitlist_promoted_mail(promoted)
        return promoted
