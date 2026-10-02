"""Campaigns on the organisation's dashboard: the list with results, a draft's
page with its previews and audience, sending a test, launching and cancelling
(mailing.campaigns). Dojo mailings show here too, read-only."""

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from accounts.organisation import Area, require_area
from campaigns import dojo_audiences
from campaigns import services as campaigns
from campaigns.dojo_views import mail_previews
from campaigns.forms import CampaignForm
from campaigns.models import Campaign
from dojos.models import Dojo
from mailing.models import EmailTemplate
from mailing.rendering import render as render_template

from .common import AUDIENCE_SAMPLE


@login_required
def campaign_list(request):
    """The organisation's campaigns and every dojo's own mailings
    (DATA_MODEL.md §25), filtered by who sent them (`from`: "organisation",
    "dojos" or a dojo's id)."""
    require_area(request, Area.COMMUNICATION)
    shown = Campaign.objects.select_related("segment", "dojo").order_by("-created_at")
    source = request.GET.get("from", "")
    if source == "organisation":
        shown = shown.filter(dojo__isnull=True)
    elif source == "dojos":
        shown = shown.filter(dojo__isnull=False)
    elif source.isdigit():
        shown = shown.filter(dojo_id=int(source))
    rows = [(c, campaigns.stats(c), _dojo_audience(c)) for c in shown]
    dojos = Dojo.objects.filter(pk__in=Campaign.objects.exclude(dojo=None).values("dojo_id")).order_by("name")
    return render(
        request,
        "campaigns/manage/campaign_list.html",
        {"rows": rows, "active": "campaigns", "source": source, "dojos": dojos},
    )


def _dojo_audience(campaign):
    if not campaign.is_dojo_mailing:
        return ""
    return dojo_audiences.describe(campaign.audience, campaign.dojo, campaign.audience_params)


@login_required
def campaign_create(request):
    require_area(request, Area.COMMUNICATION)
    form = CampaignForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        campaign = form.save()
        messages.success(request, _("Campaign saved as a draft."))
        return redirect("manage_campaign_detail", campaign_id=campaign.pk)
    return render(request, "campaigns/manage/campaign_form.html", {"form": form, "active": "campaigns"})


def _previews(campaign, user):
    """A campaign's (or journey's) mail in every language its template has,
    rendered for the viewer as the recipient."""
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
    require_area(request, Area.COMMUNICATION)
    campaign = get_object_or_404(Campaign.objects.select_related("segment", "launched_by", "dojo"), pk=campaign_id)
    form = None
    # A dojo's mailing is the dojo's to write and send; the organisation
    # sees it and can stop it (DATA_MODEL.md §25).
    if campaign.is_editable and not campaign.is_dojo_mailing:
        form = CampaignForm(request.POST or None, instance=campaign)
        if request.method == "POST" and form.is_valid():
            form.save()
            messages.success(request, _("Campaign saved."))
            return redirect("manage_campaign_detail", campaign_id=campaign.pk)
    audience = campaigns.audience(campaign)
    return render(
        request,
        "campaigns/manage/campaign_detail.html",
        {
            "campaign": campaign,
            "form": form,
            "active": "campaigns",
            "stats": campaigns.stats(campaign),
            "audience_sample": audience.order_by("pk")[:AUDIENCE_SAMPLE],
            "problems": campaigns.launch_problems(campaign) if campaign.is_editable else [],
            "previews": mail_previews(campaign) if campaign.is_dojo_mailing else _previews(campaign, request.user),
            "dojo_audience": _dojo_audience(campaign),
        },
    )


def _campaign_action(request, campaign_id, action, success, for_dojo_mailings=False):
    require_area(request, Area.COMMUNICATION)
    campaign = get_object_or_404(Campaign, pk=campaign_id)
    if campaign.is_dojo_mailing and not (for_dojo_mailings and not campaign.is_editable):
        # Testing and sending a dojo's mail is its champion's; the
        # organisation can only stop one that's going out.
        messages.error(request, _("This is a dojo's own mail: only its champion tests and sends it."))
        return redirect("manage_campaign_detail", campaign_id=campaign.pk)
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
        request,
        campaign_id,
        lambda c: campaigns.send_test(c, request.user),
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
    return _campaign_action(
        request, campaign_id, campaigns.cancel, lambda c: "Campaign cancelled.", for_dojo_mailings=True
    )
