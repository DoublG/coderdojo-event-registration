"""A dojo's own mail to its families (DATA_MODEL.md §25): the *Mail* pages
of the dojo's admin area. Anyone on the dojo's managing team sees the list
and what was sent; writing, testing, sending and cancelling need SEND_MAIL
(the champion). A mailing is a `Campaign` with the dojo set, so everything
it does goes through mailing.campaigns, and the audiences through
mailing.dojo_audiences. The team sees how many families a mail reaches,
never who they are."""

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from core.content_languages import language_name
from dojos.access import SEND_MAIL, require_dojo_access
from dojos.views import _admin_context

from . import campaigns, dojo_audiences
from .forms import DojoMailingForm
from .models import Campaign
from .rendering import TemplateMissing
from .rendering import render as render_mail

EXAMPLE_RECIPIENT = "Ellen"


def _mailing(access, campaign_id):
    """One of this dojo's mailings (another dojo's is a 404)."""
    return get_object_or_404(Campaign, pk=campaign_id, dojo=access.dojo)


def _context(request, access, **extra):
    dojo = access.dojo
    return {
        "active": "mail",
        "limit": settings.MAILING_DOJO_MAILINGS_PER_30_DAYS,
        "launched": campaigns.dojo_launches(dojo),
        **_admin_context(request, access),
        **extra,
    }


def _previews(campaign):
    """The mail as a family would get it, per dojo language."""
    previews = []
    for language in campaign.content_languages():
        context = {
            **campaigns.dojo_context(campaign, _Reader(language)),
            "recipient_name": EXAMPLE_RECIPIENT,
            "site_url": settings.SITE_URL,
            "unsubscribe_url": settings.SITE_URL + "/mail/unsubscribe/…/",
        }
        try:
            subject, body = render_mail(campaigns.DOJO_TEMPLATE, language, context)
        except TemplateMissing:
            return []
        previews.append({"language": language_name(language), "code": language, "subject": subject, "body": body})
    return previews


class _Reader:
    """Stands in for a family reading in `language`, for the preview."""

    def __init__(self, language):
        self.preferred_language = language


def _reach(dojo, audience, params):
    try:
        reached, left_out = dojo_audiences.reach(audience, dojo, params)
    except dojo_audiences.DojoAudienceError as error:
        return {"error": str(error)}
    return {"reached": reached, "left_out": left_out, "needs_consent": dojo_audiences.get(audience).needs_consent}


@login_required
def dojo_mail_list(request, dojo_id):
    """The dojo's mailings, drafts first, with how each one went."""
    access = require_dojo_access(request, dojo_id)
    mailings = list(access.dojo.mailings.order_by("-created_at"))
    rows = [
        {
            "campaign": c,
            "audience": dojo_audiences.describe(c.audience, access.dojo, c.audience_params),
            "stats": campaigns.stats(c) if c.launched_at else None,
        }
        for c in mailings
    ]
    return render(request, "mailing/dojo/mail_list.html", _context(request, access, rows=rows))


@login_required
def dojo_mail_create(request, dojo_id):
    access = require_dojo_access(request, dojo_id, SEND_MAIL)
    form = DojoMailingForm(request.POST or None, dojo=access.dojo)
    if request.method == "POST" and form.is_valid():
        campaign = form.save(commit=False)
        campaign.created_by = request.user
        campaign.save()
        messages.success(request, _("Draft saved. Check the preview, send yourself a test, then send it."))
        return redirect("dojo_mail_detail", dojo_id=access.dojo.id, campaign_id=campaign.pk)
    return render(request, "mailing/dojo/mail_form.html", _context(request, access, form=form, campaign=None))


@login_required
def dojo_mail_detail(request, dojo_id, campaign_id):
    """A draft: edit it (SEND_MAIL), with the preview and what's still in
    the way of sending. Once sent: what went out and how it went."""
    access = require_dojo_access(request, dojo_id)
    campaign = _mailing(access, campaign_id)
    editable = campaign.is_editable and access.can_send_mail
    form = None
    if editable:
        form = DojoMailingForm(request.POST or None, dojo=access.dojo, instance=campaign)
        if request.method == "POST" and form.is_valid():
            form.save()
            messages.success(request, _("Draft saved."))
            return redirect("dojo_mail_detail", dojo_id=access.dojo.id, campaign_id=campaign.pk)
    elif request.method == "POST":
        return redirect("dojo_mail_detail", dojo_id=access.dojo.id, campaign_id=campaign.pk)
    return render(
        request,
        "mailing/dojo/mail_detail.html" if not editable else "mailing/dojo/mail_form.html",
        _context(
            request,
            access,
            campaign=campaign,
            form=form,
            audience=dojo_audiences.describe(campaign.audience, access.dojo, campaign.audience_params),
            reach=_reach(access.dojo, campaign.audience, campaign.audience_params) if campaign.is_editable else None,
            problems=campaigns.launch_problems(campaign) if campaign.is_editable else [],
            previews=_previews(campaign),
            stats=campaigns.stats(campaign) if campaign.launched_at else None,
        ),
    )


@login_required
def dojo_mail_reach(request, dojo_id):
    """htmx: how many families the audience picked in the form reaches."""
    access = require_dojo_access(request, dojo_id, SEND_MAIL)
    params = {name: request.GET.get(name) for name in DojoMailingForm.PARAM_FIELDS}
    reach = _reach(access.dojo, request.GET.get("audience", ""), params)
    return render(request, "mailing/dojo/_reach.html", {"reach": reach})


@login_required
@require_POST
def dojo_mail_test(request, dojo_id, campaign_id):
    access = require_dojo_access(request, dojo_id, SEND_MAIL)
    campaign = _mailing(access, campaign_id)
    try:
        campaigns.send_test(campaign, request.user)
    except campaigns.CampaignError as error:
        messages.error(request, str(error))
    else:
        messages.success(request, _("A test is on its way to %(email)s.") % {"email": request.user.email})
    return redirect("dojo_mail_detail", dojo_id=access.dojo.id, campaign_id=campaign.pk)


@login_required
@require_POST
def dojo_mail_launch(request, dojo_id, campaign_id):
    access = require_dojo_access(request, dojo_id, SEND_MAIL)
    campaign = _mailing(access, campaign_id)
    try:
        campaigns.launch(campaign, request.user)
    except campaigns.CampaignError as error:
        messages.error(request, str(error))
    else:
        messages.success(request, _("Sent. The mails go out over the next few minutes."))
    return redirect("dojo_mail_detail", dojo_id=access.dojo.id, campaign_id=campaign.pk)


@login_required
@require_POST
def dojo_mail_cancel(request, dojo_id, campaign_id):
    access = require_dojo_access(request, dojo_id, SEND_MAIL)
    campaign = _mailing(access, campaign_id)
    if campaign.is_editable:
        campaign.delete()
        messages.success(request, _("Draft deleted."))
        return redirect("dojo_mail_list", dojo_id=access.dojo.id)
    try:
        campaigns.cancel(campaign)
    except campaigns.CampaignError as error:
        messages.error(request, str(error))
    else:
        messages.success(request, _("Stopped. Mails that hadn't gone out yet won't be sent."))
    return redirect("dojo_mail_detail", dojo_id=access.dojo.id, campaign_id=campaign.pk)
