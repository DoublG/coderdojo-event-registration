"""The organisation dashboard's Promotions page (/manage/promotions/, shell
core/_manage_base.html): which events are featured where on the public
site (content.Promotion, DATA_MODEL.md §12). Organisation admin role only
(accounts.organisation.require_organisation_admin)."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from accounts.organisation import require_organisation_admin
from events.models import Event

from .forms import PromotionForm
from .models import Promotion

SHOWING = "showing"
SCHEDULED = "scheduled"
ENDED = "ended"
HIDDEN = "hidden"


def promotion_state(promotion, visible_event_ids, now=None):
    """Where a promotion stands: showing, scheduled (starts later), ended,
    or hidden (its event isn't on the public site, e.g. still a draft)."""
    now = now or timezone.now()
    if now >= promotion.effective_end or now >= promotion.event.end_time:
        return ENDED
    if promotion.event_id not in visible_event_ids:
        return HIDDEN
    if now < promotion.starts_at:
        return SCHEDULED
    return SHOWING


@login_required
def promotion_list(request):
    require_organisation_admin(request)
    now = timezone.now()
    promotions = list(Promotion.objects.order_by("placement", "rank", "starts_at", "id"))
    visible = set(
        Event.objects.visible().filter(pk__in={p.event_id for p in promotions}).values_list("pk", flat=True)
    )
    groups = []
    for value, label in Promotion.PLACEMENT_CHOICES:
        rows = [(p, promotion_state(p, visible, now)) for p in promotions if p.placement == value]
        # Ended promotions go last, so what's live reads first.
        rows.sort(key=lambda row: row[1] == ENDED)
        groups.append({"label": label, "rows": rows})
    return render(request, "content/manage/promotion_list.html", {"groups": groups, "active": "promotions"})


@login_required
def promotion_create(request):
    require_organisation_admin(request)
    initial = {"event": request.GET.get("event")} if request.GET.get("event") else None
    form = PromotionForm(request.POST or None, request.FILES or None, initial=initial)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, _("Promotion saved."))
        return redirect("manage_promotion_list")
    return render(request, "content/manage/promotion_form.html", {"form": form, "active": "promotions"})


@login_required
def promotion_detail(request, promotion_id):
    require_organisation_admin(request)
    promotion = get_object_or_404(Promotion, pk=promotion_id)
    form = PromotionForm(request.POST or None, request.FILES or None, instance=promotion)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, _("Promotion saved."))
        return redirect("manage_promotion_list")
    return render(request, "content/manage/promotion_form.html", {
        "form": form, "promotion": promotion, "active": "promotions",
    })


@login_required
@require_POST
def promotion_delete(request, promotion_id):
    require_organisation_admin(request)
    promotion = get_object_or_404(Promotion, pk=promotion_id)
    promotion.delete()
    messages.success(request, _("Promotion removed."))
    return redirect("manage_promotion_list")
