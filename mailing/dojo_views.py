"""A dojo's own mail to its families (DATA_MODEL.md §25): the *Mail* pages
of the dojo's admin area. Anyone on the dojo's managing team sees the list
and what was sent; writing, testing, sending and cancelling need SEND_MAIL
(the champion). A mailing is a `Campaign` with the dojo set, so everything
it does goes through mailing.campaigns, and the audiences through
mailing.dojo_audiences. The team sees how many families a mail reaches,
never who they are."""

from datetime import timedelta

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Min, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy
from django.views.decorators.http import require_POST

from core.content_languages import language_name
from dojos.access import SEND_MAIL, require_dojo_access
from dojos.views import _admin_context

from . import campaigns, dojo_audiences, queue_status, services
from .forms import DojoMailingForm
from .models import Campaign, EmailMessage
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


def mail_previews(campaign):
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
            subject, body = render_mail(campaign.template_key, language, context)
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
    audience = dojo_audiences.get(audience)
    return {
        "reached": reached,
        "left_out": left_out,
        "needs_consent": audience.needs_consent,
        "team": audience.is_team,
    }


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
            previews=mail_previews(campaign),
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


# --- the dojo's mail queue ------------------------------------------------------------

QUEUE_RECENT_DAYS = 30

# EmailMessage.status_reason of held-back mail, in words for the dojo's team.
HELD_BACK_REASONS = {
    services.MUTED_DOJO: gettext_lazy("The family stopped your dojo's news."),
    services.NOT_SUBSCRIBED: gettext_lazy("They switched off this kind of mail (news from dojos, or volunteering)."),
    services.BLOCKED: gettext_lazy("The address is blocked: earlier mail to it bounced, or it was marked as spam."),
    services.INACTIVE: gettext_lazy("The account was switched off."),
    services.NO_ADDRESS: gettext_lazy("The account has no email address."),
    services.WRONG_ACCOUNT_TYPE: gettext_lazy("This kind of mail doesn't go to this kind of account."),
    campaigns.CANCELLED: gettext_lazy("You stopped the mail before it went out."),
}


@login_required
def dojo_mail_queue(request, dojo_id):
    """What happened to the dojo's mail (its own mailings and the automatic
    "new sessions" mail): waiting, sent, not delivered and held back, per
    mail and in counts. Read-only, and never the families' addresses
    (DATA_MODEL.md §25, decision 10): a failure's own text can hold an
    address, so it's shown as "not delivered" only."""
    access = require_dojo_access(request, dojo_id)
    now = timezone.now()
    since = now - timedelta(days=QUEUE_RECENT_DAYS)
    Status = EmailMessage.Status
    # Everything from the dojo: news to its families, and mail to its team.
    mail = EmailMessage.objects.filter(dojo=access.dojo)
    open_statuses = [Status.PENDING, Status.SENDING]
    shown = mail.filter(Q(created_at__gte=since) | Q(status__in=open_statuses))

    rows = {}
    for entry in shown.values("campaign_id", "campaign__subject", "template_key", "is_test", "status").annotate(
        n=Count("id"), first=Min("created_at")
    ):
        key = ("test",) if entry["is_test"] else (entry["campaign_id"] or entry["template_key"],)
        row = rows.setdefault(
            key,
            {
                "campaign_id": None if entry["is_test"] else entry["campaign_id"],
                "label": _mail_label(entry),
                "first": entry["first"],
                "waiting": 0,
                "sent": 0,
                "not_delivered": 0,
                "held_back": 0,
            },
        )
        row["first"] = min(row["first"], entry["first"])
        row[_column(entry["status"])] += entry["n"]

    held_back = {}
    recent_held = mail.filter(status=Status.SUPPRESSED, created_at__gte=since, is_test=False)
    for entry in recent_held.values("status_reason").annotate(n=Count("id")):
        label = str(HELD_BACK_REASONS.get(entry["status_reason"], _("Another reason.")))
        held_back[label] = held_back.get(label, 0) + entry["n"]

    oldest = queue_status.oldest_due(now)
    counts = {
        "waiting": mail.filter(status__in=open_statuses).count(),
        "sent_today": mail.filter(status=Status.SENT, sent_at__gte=now - timedelta(days=1)).count(),
        "not_delivered": mail.filter(status__in=[Status.FAILED, Status.BOUNCED], created_at__gte=since).count(),
        "held_back": recent_held.count(),
    }
    return render(
        request,
        "mailing/dojo/mail_queue.html",
        _context(
            request,
            access,
            counts=counts,
            rows=sorted(rows.values(), key=lambda r: r["first"], reverse=True),
            held_back=sorted(held_back.items(), key=lambda item: -item[1]),
            recent_days=QUEUE_RECENT_DAYS,
            stalled=queue_status.is_stalled(oldest, now),
            oldest_due=oldest,
        ),
    )


def _mail_label(entry):
    if entry["is_test"]:
        return _("Tests sent to yourself")
    if entry["campaign_id"]:
        return entry["campaign__subject"]
    if entry["template_key"] == "new_sessions_at_dojo":
        return _("New sessions (the automatic mail)")
    return entry["template_key"]


def _column(status):
    Status = EmailMessage.Status
    if status in (Status.PENDING, Status.SENDING):
        return "waiting"
    if status == Status.SENT:
        return "sent"
    if status in (Status.FAILED, Status.BOUNCED):
        return "not_delivered"
    return "held_back"
