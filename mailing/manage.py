"""The organisation's management dashboard for mail (/manage/…, shell
core/_manage_base.html): campaigns and segments. Only the organisation's
admin role gets in (accounts.organisation.require_organisation_admin);
every campaign change goes through mailing.campaigns."""

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from accounts.organisation import require_organisation_admin

from . import campaigns
from .forms import CampaignForm
from .models import Campaign, EmailTemplate, Segment
from .rendering import render as render_template
from .segmentation.resolver import SegmentResolver

AUDIENCE_SAMPLE = 10


@login_required
def manage_home(request):
    require_organisation_admin(request)
    return redirect("manage_campaign_list")


@login_required
def campaign_list(request):
    require_organisation_admin(request)
    rows = [(c, campaigns.stats(c)) for c in Campaign.objects.select_related("segment").order_by("-created_at")]
    return render(request, "mailing/manage/campaign_list.html", {"rows": rows, "active": "campaigns"})


@login_required
def campaign_create(request):
    require_organisation_admin(request)
    form = CampaignForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        campaign = form.save()
        messages.success(request, "Campaign saved as a draft.")
        return redirect("manage_campaign_detail", campaign_id=campaign.pk)
    return render(request, "mailing/manage/campaign_form.html", {"form": form, "active": "campaigns"})


def _previews(campaign, user):
    """The campaign's mail in every language its template has, rendered
    for the viewer as the recipient."""
    context = {
        "recipient_name": user.first_name or user.get_username(),
        "site_url": settings.SITE_URL,
        "unsubscribe_url": settings.SITE_URL + "/mail/unsubscribe/…/",
        **(campaign.context or {}),
    }
    previews = []
    for template in EmailTemplate.objects.filter(key=campaign.template_key).order_by("language"):
        subject, body = render_template(template.key, template.language, context)
        previews.append({"language": template.get_language_display(), "subject": subject, "body": body})
    return previews


@login_required
def campaign_detail(request, campaign_id):
    require_organisation_admin(request)
    campaign = get_object_or_404(Campaign.objects.select_related("segment", "launched_by"), pk=campaign_id)
    form = None
    if campaign.is_editable:
        form = CampaignForm(request.POST or None, instance=campaign)
        if request.method == "POST" and form.is_valid():
            form.save()
            messages.success(request, "Campaign saved.")
            return redirect("manage_campaign_detail", campaign_id=campaign.pk)
    audience = campaigns.audience(campaign)
    return render(request, "mailing/manage/campaign_detail.html", {
        "campaign": campaign, "form": form, "active": "campaigns",
        "stats": campaigns.stats(campaign),
        "audience_sample": audience.order_by("pk")[:AUDIENCE_SAMPLE],
        "problems": campaigns.launch_problems(campaign) if campaign.is_editable else [],
        "previews": _previews(campaign, request.user),
    })


def _campaign_action(request, campaign_id, action, success):
    require_organisation_admin(request)
    campaign = get_object_or_404(Campaign, pk=campaign_id)
    try:
        action(campaign)
    except campaigns.CampaignError as error:
        messages.error(request, str(error))
    else:
        messages.success(request, success(campaign))
    return redirect("manage_campaign_detail", campaign_id=campaign.pk)


@login_required
@require_POST
def campaign_test(request, campaign_id):
    return _campaign_action(
        request, campaign_id, lambda c: campaigns.send_test(c, request.user),
        lambda c: f"A test is on its way to {request.user.email}.",
    )


@login_required
@require_POST
def campaign_launch(request, campaign_id):
    def success(campaign):
        if campaign.scheduled_at:
            return f"Launched: it goes out on {campaign.scheduled_at:%d/%m/%Y at %H:%M}."
        return "Launched: the mail is being queued and goes out within minutes."
    return _campaign_action(request, campaign_id, lambda c: campaigns.launch(c, request.user), success)


@login_required
@require_POST
def campaign_cancel(request, campaign_id):
    return _campaign_action(request, campaign_id, campaigns.cancel, lambda c: "Campaign cancelled.")


@login_required
def segment_list(request):
    require_organisation_admin(request)
    resolver = SegmentResolver()
    rows = [(s, resolver.resolve(s).count()) for s in Segment.objects.order_by("name")]
    return render(request, "mailing/manage/segment_list.html", {"rows": rows, "active": "segments"})
