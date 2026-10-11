"""The organisation dashboard's Awards page (/manage/awards/, shell
core/_manage_base.html): the badges ninjas can earn (events.Badge). Only the
organisation defines awards, here or in the Django admin; dojo teams never
create them, they only award them (events.awards). The Ninjas area only
(accounts.organisation.require_area, the admin role, DATA_MODEL.md §23).

Assign awards (/manage/awards/assign/) lets the organisation award a one-off
badge directly to a ninja, with no dojo or attendance tie — for its own
events (Coolest Projects, CoderDojo for Girls) whose registrations may live
on another system entirely (events.awards.award_badge_as_organisation)."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from accounts.models import Ninja
from accounts.organisation import Area, require_area

from .awards import BadgeError, award_badge_as_organisation
from .forms import AssignBadgeForm, BadgeForm
from .models import Badge

SEARCH_LIMIT = 25


def _with_counts(queryset):
    return queryset.annotate(
        earned_count=Count("ninja_badges", filter=Q(ninja_badges__earned_date__isnull=False)),
        ninja_count=Count("ninja_badges"),
    )


@login_required
def badge_list(request):
    require_area(request, Area.NINJAS)
    badges = _with_counts(Badge.objects.select_related("grants_belt").prefetch_related("dojos"))
    return render(
        request,
        "events/manage/badge_list.html",
        {
            "one_offs": [b for b in badges if b.kind == Badge.ONE_OFF],
            "milestones": [b for b in badges if b.kind == Badge.MILESTONE],
            "active": "awards",
        },
    )


@login_required
def badge_create(request):
    require_area(request, Area.NINJAS)
    form = BadgeForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, _("Award saved."))
        return redirect("manage_badge_list")
    return render(request, "events/manage/badge_form.html", {"form": form, "active": "awards"})


@login_required
def badge_detail(request, badge_id):
    require_area(request, Area.NINJAS)
    badge = get_object_or_404(_with_counts(Badge.objects.all()), pk=badge_id)
    form = BadgeForm(request.POST or None, request.FILES or None, instance=badge)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, _("Award saved."))
        return redirect("manage_badge_list")
    return render(request, "events/manage/badge_form.html", {"form": form, "badge": badge, "active": "awards"})


@login_required
@require_POST
def badge_delete(request, badge_id):
    """Removes an award nobody has yet. One that ninjas already have (or are
    working toward) stays: deleting it would take it off their pages."""
    require_area(request, Area.NINJAS)
    badge = get_object_or_404(Badge, pk=badge_id)
    if badge.ninja_badges.exists():
        messages.error(request, _("Ninjas already have this award, so it can't be removed."))
        return redirect("manage_badge_detail", badge_id=badge.id)
    badge.delete()
    messages.success(request, _("Award removed."))
    return redirect("manage_badge_list")


@login_required
def badge_assign(request):
    """Find a ninja to award a one-off badge to directly (badge_assign_ninja)
    — for the organisation's own events, whose sign-ups may happen on
    another system entirely, with no local attendance list to award it from.
    The search box is a typeahead (htmx, re-fetching just the results as you
    type); an htmx request gets only the results partial back, a plain GET
    (no JavaScript) the whole page."""
    require_area(request, Area.NINJAS)
    query = request.GET.get("q", "").strip()
    ninjas = []
    if query:
        ninjas = list(
            Ninja.objects.filter(Q(name__icontains=query) | Q(family_name__icontains=query))
            .select_related("home_dojo")
            .prefetch_related("guardianships__guardian")
            .order_by("name", "family_name")[:SEARCH_LIMIT]
        )
    context = {"query": query, "ninjas": ninjas, "search_limit": SEARCH_LIMIT, "active": "awards_assign"}
    if request.headers.get("HX-Request") == "true":
        return render(request, "events/manage/_badge_assign_results.html", context)
    return render(request, "events/manage/badge_assign.html", context)


@login_required
def badge_assign_ninja(request, ninja_id):
    """Award this ninja a one-off badge directly, as the organisation
    (events.awards.award_badge_as_organisation) — never a milestone, and
    never one they already have; the organisation can award any one-off
    badge here, whichever dojos (if any) Badge.dojos names."""
    require_area(request, Area.NINJAS)
    ninja = get_object_or_404(Ninja, pk=ninja_id)
    earned_ids = ninja.badges.filter(earned_date__isnull=False).values_list("badge_id", flat=True)
    form = AssignBadgeForm(request.POST or None)
    form.fields["badge"].queryset = (
        Badge.objects.filter(kind=Badge.ONE_OFF).exclude(id__in=earned_ids).order_by("name")
    )
    if request.method == "POST" and form.is_valid():
        badge = form.cleaned_data["badge"]
        try:
            award_badge_as_organisation(ninja, badge, request.user, note=form.cleaned_data["note"])
        except BadgeError as error:
            form.add_error("badge", str(error))
        else:
            messages.success(
                request, _("%(badge)s awarded to %(ninja)s.") % {"badge": badge.name, "ninja": ninja.full_name}
            )
            return redirect("manage_badge_assign_ninja", ninja_id=ninja.id)
    earned = ninja.badges.select_related("badge").filter(earned_date__isnull=False).order_by("-earned_date")
    return render(
        request,
        "events/manage/badge_assign_ninja.html",
        {"ninja": ninja, "form": form, "earned": earned, "active": "awards_assign"},
    )
