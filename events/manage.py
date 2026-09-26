"""The organisation dashboard's Awards page (/manage/awards/, shell
core/_manage_base.html): the badges ninjas can earn (events.Badge). Only the
organisation defines awards, here or in the Django admin; dojo teams never
create them, they only award them (events.awards). Organisation admin role
only (accounts.organisation.require_organisation_admin)."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from accounts.organisation import require_organisation_admin

from .forms import BadgeForm
from .models import Badge


def _with_counts(queryset):
    return queryset.annotate(
        earned_count=Count("ninja_badges", filter=Q(ninja_badges__earned_date__isnull=False)),
        ninja_count=Count("ninja_badges"),
    )


@login_required
def badge_list(request):
    require_organisation_admin(request)
    badges = _with_counts(Badge.objects.select_related("grants_belt"))
    return render(request, "events/manage/badge_list.html", {
        "one_offs": [b for b in badges if b.kind == Badge.ONE_OFF],
        "milestones": [b for b in badges if b.kind == Badge.MILESTONE],
        "active": "awards",
    })


@login_required
def badge_create(request):
    require_organisation_admin(request)
    form = BadgeForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, _("Award saved."))
        return redirect("manage_badge_list")
    return render(request, "events/manage/badge_form.html", {"form": form, "active": "awards"})


@login_required
def badge_detail(request, badge_id):
    require_organisation_admin(request)
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
    require_organisation_admin(request)
    badge = get_object_or_404(Badge, pk=badge_id)
    if badge.ninja_badges.exists():
        messages.error(request, _("Ninjas already have this award, so it can't be removed."))
        return redirect("manage_badge_detail", badge_id=badge.id)
    badge.delete()
    messages.success(request, _("Award removed."))
    return redirect("manage_badge_list")
