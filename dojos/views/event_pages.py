"""A dojo's sessions in its admin area: the events list, creating and editing a
session, its status, and the organisation's Promotions card."""

from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme

from accounts.organisation import Area, has_area
from content.manage import promotion_state
from events.forms import EventForm
from events.models import Event

from ..access import (
    MANAGE_EVENTS,
    require_dojo_access,
)
from .common import _admin_context


@login_required
def dojo_event_list(request, dojo_id):
    access = require_dojo_access(request, dojo_id)
    dojo = access.dojo
    events = dojo.event_set.with_confirmed_count().order_by("-start_time")
    return render(
        request,
        "dojos/dojo_event_list.html",
        {
            "events": events,
            "active": "events",
            **_admin_context(request, access),
        },
    )


@login_required
def dojo_event_create(request, dojo_id):
    """A new session always starts out Draft (Event.status' model default)
    — see EventForm's docstring for why status isn't a field on this form
    at all. The owner publishes it (draft -> open) from the events list
    or its detail page once it's ready, via dojo_event_set_status."""
    access = require_dojo_access(request, dojo_id, MANAGE_EVENTS)
    dojo = access.dojo

    if request.method == "POST":
        form = EventForm(request.POST, request.FILES, instance=Event(dojo=dojo), dojo=dojo)
        if form.is_valid():
            form.save()
            return redirect("dojo_event_list", dojo_id=dojo.id)
    else:
        form = EventForm(instance=Event(dojo=dojo), dojo=dojo)

    return render(
        request,
        "dojos/dojo_event_create.html",
        {
            "form": form,
            "active": "events",
            **_admin_context(request, access),
        },
    )


@login_required
def dojo_event_detail(request, dojo_id, event_id):
    """Edit an existing event — same EventForm as dojo_event_create, just
    bound to an existing instance (EventForm.__init__ pre-fills event_date/
    start_time/end_time from it). Re-renders in place on success, same
    "no redirect, just show a saved banner" convention as dojo_manage,
    since this is an edit-in-place settings-style form, not a one-shot
    creation. Status is changed separately, via dojo_event_set_status —
    the status card at the top of the template posts there directly, so
    saving the form never touches status and vice versa."""
    access = require_dojo_access(request, dojo_id, MANAGE_EVENTS)
    dojo = access.dojo
    event = get_object_or_404(Event, id=event_id, dojo=dojo)
    saved = False

    if request.method == "POST":
        form = EventForm(request.POST, request.FILES, instance=event, dojo=dojo)
        if form.is_valid():
            event = form.save()
            saved = True
    else:
        form = EventForm(instance=event, dojo=dojo)

    return render(
        request,
        "dojos/dojo_event_detail.html",
        {
            "event": event,
            "form": form,
            "saved": saved,
            "active": "events",
            **_event_promotions_context(request, event),
            **_admin_context(request, access),
        },
    )


def _event_promotions_context(request, event):
    """The event page's Promotions card (DATA_MODEL.md §20): only for an
    account with the organisation dashboard's Public site area (§23: the
    admin role), since promoting is the organisation's work (content.manage), the event's promotions with where each stands, and
    whether it can still get one (the promotion form offers events that
    haven't ended)."""
    if not has_area(request.user, Area.PUBLIC_SITE):
        return {"can_promote": False}
    promotions = list(event.promotions.order_by("placement", "rank", "starts_at", "id"))
    visible = set(Event.objects.visible().filter(pk=event.pk).values_list("pk", flat=True))
    now = timezone.now()
    return {
        "can_promote": True,
        "event_promotions": [(p, promotion_state(p, visible, now)) for p in promotions],
        "event_promotable": event.end_time > now,
    }


@login_required
def dojo_event_set_status(request, dojo_id, event_id):
    """Sets an event's status directly — any of draft/open/closed, from any
    other one. Not a one-way lifecycle: an owner can reopen a closed
    session, or pull a published one back to draft (hiding it from the
    public site again — existing registrations are kept, not cancelled).
    Posting an absolute target status (rather than a "next step" action)
    keeps a stale page or double-click harmless: it just re-applies the
    same status. An unknown status value is ignored.

    Redirects back to `next` (posted by whichever page linked here — the
    list or the detail page) when it's a safe same-site URL, else falls
    back to the events list."""
    access = require_dojo_access(request, dojo_id, MANAGE_EVENTS)
    dojo = access.dojo
    event = get_object_or_404(Event, id=event_id, dojo=dojo)

    if request.method == "POST":
        new_status = request.POST.get("status")
        if new_status in dict(Event.STATUS_CHOICES) and new_status != event.status:
            event.status = new_status
            event.save(update_fields=["status"])

    next_url = request.POST.get("next")
    if next_url and url_has_allowed_host_and_scheme(
        next_url, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        return redirect(next_url)
    return redirect("dojo_event_list", dojo_id=dojo.id)
