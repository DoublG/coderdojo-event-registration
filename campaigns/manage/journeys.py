"""Journeys, standing campaigns (mailing.journeys): the list, creating one, its
page with who gets it next, activating, pausing and sending a test."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from accounts.organisation import Area, require_area
from campaigns import journeys
from campaigns import services as campaigns
from campaigns.forms import JourneyForm
from campaigns.models import Journey

from .campaigns import _previews
from .common import AUDIENCE_SAMPLE

# --- journeys ---------------------------------------------------------------------------


@login_required
def journey_list(request):
    require_area(request, Area.COMMUNICATION)
    rows = [(j, journeys.stats(j)) for j in Journey.objects.select_related("segment").order_by("name")]
    return render(request, "campaigns/manage/journey_list.html", {"rows": rows, "active": "journeys"})


@login_required
def journey_create(request):
    require_area(request, Area.COMMUNICATION)
    form = JourneyForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        journey = form.save()
        messages.success(request, _("Journey saved. It's paused until you activate it."))
        return redirect("manage_journey_detail", journey_id=journey.pk)
    return render(request, "campaigns/manage/journey_form.html", {"form": form, "active": "journeys"})


@login_required
def journey_detail(request, journey_id):
    require_area(request, Area.COMMUNICATION)
    journey = get_object_or_404(Journey.objects.select_related("segment"), pk=journey_id)
    form = JourneyForm(request.POST or None, instance=journey)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, _("Journey saved. Changes apply from the next daily run."))
        return redirect("manage_journey_detail", journey_id=journey.pk)
    return render(
        request,
        "campaigns/manage/journey_detail.html",
        {
            "journey": journey,
            "form": form,
            "active": "journeys",
            "stats": journeys.stats(journey),
            "due_sample": journeys.due(journey).order_by("pk")[:AUDIENCE_SAMPLE] if journey.segment_id else [],
            "problems": journeys.problems(journey),
            "previews": _previews(journey, request.user),
            "recent": journey.deliveries.select_related("email").order_by("-created_at")[:AUDIENCE_SAMPLE],
        },
    )


def _journey_action(request, journey_id, action, success):
    require_area(request, Area.COMMUNICATION)
    journey = get_object_or_404(Journey, pk=journey_id)
    try:
        action(journey)
    except campaigns.CampaignError as error:
        messages.error(request, str(error))
    else:
        messages.success(request, success)
    return redirect("manage_journey_detail", journey_id=journey.pk)


@login_required
@require_POST
def journey_activate(request, journey_id):
    return _journey_action(
        request, journey_id, journeys.activate, "Active: it runs every day at 18:00 for everyone newly matching."
    )


@login_required
@require_POST
def journey_pause(request, journey_id):
    return _journey_action(request, journey_id, journeys.pause, "Paused.")


@login_required
@require_POST
def journey_test(request, journey_id):
    return _journey_action(
        request,
        journey_id,
        lambda j: journeys.send_test(j, request.user),
        f"A test is on its way to {request.user.email}.",
    )
