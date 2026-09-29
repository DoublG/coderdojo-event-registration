"""Campaigns: one mailing to a segment's audience (DATA_MODEL.md §11,
phase 8). Every change of a campaign's state goes through here; the views
in mailing.manage only call these (CampaignError carries a message for the
person using the dashboard).

    draft ──launch──▶ queued ──(its time comes)──▶ sending ──(all out)──▶ completed
      ▲                 │                             │
      └─────────────────┴──────────cancel─────────────┘──▶ cancelled

- launch() checks the campaign, freezes the segment's definition in
  `segment_snapshot` and marks it queued. It doesn't queue mail itself.
- launch_due() (beat, every minute) starts every queued campaign whose
  `scheduled_at` has come (or that has none) with the launch_campaign task,
  resumes one whose queuing was interrupted, and completes those whose
  mail is all out.
- queue_mail() (the launch_campaign task) resolves the frozen audience,
  only the accounts who want this kind of mail, and queues one mail each
  through mailing.services.send(). Idempotency keys make it safe to run
  again after a crash.

A dojo mailing (DATA_MODEL.md §25, `campaign.dojo` set) takes the same
path, with its own checks: always `dojo_news`, one of the prepared
audiences (mailing.dojo_audiences) instead of a segment, the dojo's text in
the `dojo_message` template (in each recipient's language when the dojo
wrote it), replies to the dojo, never to a family that muted the dojo, and
at most MAILING_DOJO_MAILINGS_PER_30_DAYS launched per dojo.
"""

from datetime import timedelta

from django.conf import settings
from django.core.cache import cache
from django.db import transaction
from django.db.models import Count, Q
from django.utils import timezone
from django.utils.translation import gettext as _

from core.content_languages import language_name

from . import dojo_audiences
from .categories import CAN_OPT_OUT, MailCategory
from .models import Campaign, ConsentEvent, DojoMailMute, EmailMessage, EmailTemplate
from .preferences import subscribed_q
from .rendering import FALLBACK_LANGUAGE
from .segmentation.resolver import SegmentResolver, serialize_segment
from .services import send

Status = Campaign.Status
LAUNCH_LOCK_SECONDS = 30 * 60


class CampaignError(Exception):
    pass


DOJO_TEMPLATE = "dojo_message"


def wanting_dojo_news(accounts, dojo):
    """The accounts among `accounts` who want `dojo`'s news: `dojo_news` on
    and the dojo not muted."""
    muted = DojoMailMute.objects.filter(dojo=dojo).values("user_id")
    return accounts.filter(subscribed_q(MailCategory.DOJO_NEWS)).exclude(pk__in=muted)


def dojo_launches(dojo, now=None):
    """How many mailings `dojo` launched in the last 30 days (a cancelled
    one only counts when some of its mail went out)."""
    since = (now or timezone.now()) - timedelta(days=30)
    launched = Campaign.objects.filter(dojo=dojo, launched_at__gte=since)
    cancelled_unsent = launched.filter(status=Status.CANCELLED).exclude(
        emailmessage__status=EmailMessage.Status.SENT, emailmessage__is_test=False
    )
    return launched.exclude(pk__in=cancelled_unsent.values("pk")).count()


def _dojo_launch_problems(campaign):
    problems = []
    if campaign.status != Status.DRAFT:
        problems.append(_("Only a draft can be sent."))
    if campaign.category != MailCategory.DOJO_NEWS:
        problems.append(_("A dojo's mail is always news from the dojo."))
    try:
        definition = dojo_audiences.definition(campaign.audience, campaign.dojo, campaign.audience_params)
    except dojo_audiences.DojoAudienceError as error:
        problems.append(str(error))
    else:
        if not wanting_dojo_news(SegmentResolver().resolve_definition(definition), campaign.dojo).exists():
            problems.append(_("Nobody would get it: the audience has no families who want your dojo's news."))
    if not campaign.subject.strip() or not campaign.message.strip():
        problems.append(
            _("Write a subject and a message in %(language)s, your dojo's main language.")
            % {"language": language_name(campaign.main_language())}
        )
    if not campaign.dojo.email:
        problems.append(_("Add your dojo's email address in its settings first: families' replies go there."))
    limit = settings.MAILING_DOJO_MAILINGS_PER_30_DAYS
    if campaign.status == Status.DRAFT and dojo_launches(campaign.dojo) >= limit:
        problems.append(
            _("Your dojo already sent %(limit)s mails in the last 30 days, the most it can send.") % {"limit": limit}
        )
    if not EmailTemplate.objects.filter(key=DOJO_TEMPLATE, language=FALLBACK_LANGUAGE).exists():
        problems.append(_("The mail layout for dojos is missing. Please tell the organisation."))
    return problems


def dojo_context(campaign, user):
    """The `dojo_message` variables for `user`: the dojo's text in their
    mail language when the dojo wrote it, else its main language."""
    from django.urls import reverse

    language = user.preferred_language or FALLBACK_LANGUAGE
    return {
        "dojo_name": campaign.dojo.name,
        # An organisation dojo, or one that isn't public, has no page of its own.
        "dojo_url": settings.SITE_URL
        + (reverse("dojo_detail", kwargs={"dojo_id": campaign.dojo_id}) if campaign.dojo.is_public else "/"),
        "subject": str(campaign.localized("subject", language)),
        "message": str(campaign.localized("message", language)),
    }


def _send_kwargs(campaign):
    if campaign.is_dojo_mailing:
        return {"dojo": campaign.dojo, "reply_to": campaign.dojo.email}
    return {}


def _mail(campaign, user):
    """(template_key, context) for `user`."""
    if campaign.is_dojo_mailing:
        return DOJO_TEMPLATE, dojo_context(campaign, user)
    return campaign.template_key, campaign.context


def launch_problems(campaign):
    """What stops `campaign` from being launched, as readable sentences."""
    if campaign.is_dojo_mailing:
        return _dojo_launch_problems(campaign)
    problems = []
    if campaign.status != Status.DRAFT:
        problems.append("Only a draft can be launched.")
    if not CAN_OPT_OUT.get(campaign.category, False):
        problems.append("A campaign must be a kind of mail people can switch off (e.g. the newsletter).")
    if not EmailTemplate.objects.filter(key=campaign.template_key, language=FALLBACK_LANGUAGE).exists():
        problems.append(f"There's no English template “{campaign.template_key}” (the fallback for every language).")
    if campaign.segment is None:
        problems.append("Pick a segment: who should get it?")
    elif not SegmentResolver().resolve(campaign.segment).exists():
        problems.append("The segment matches nobody.")
    return problems


def audience(campaign):
    """Who the campaign reaches (or reached): the frozen snapshot once
    launched, the live segment while it's a draft; only accounts who want
    this kind of mail."""
    resolver = SegmentResolver()
    if campaign.is_dojo_mailing:
        definition = campaign.segment_snapshot
        if not definition:
            try:
                definition = dojo_audiences.definition(campaign.audience, campaign.dojo, campaign.audience_params)
            except dojo_audiences.DojoAudienceError:
                definition = None
        return wanting_dojo_news(resolver.resolve_definition(definition), campaign.dojo)
    if campaign.segment_snapshot:
        accounts = resolver.resolve_definition(campaign.segment_snapshot)
    elif campaign.segment_id:
        accounts = resolver.resolve(campaign.segment)
    else:
        accounts = resolver.resolve_definition(None)  # nobody
    return accounts.filter(subscribed_q(campaign.category))


def launch(campaign, user):
    if problems := launch_problems(campaign):
        raise CampaignError(_(" ").join(problems))
    if campaign.is_dojo_mailing:
        campaign.segment_snapshot = dojo_audiences.definition(
            campaign.audience, campaign.dojo, campaign.audience_params
        )
    else:
        campaign.segment_snapshot = serialize_segment(campaign.segment)
    campaign.status = Status.QUEUED
    campaign.launched_at = timezone.now()
    campaign.launched_by = user
    campaign.save(update_fields=["segment_snapshot", "status", "launched_at", "launched_by"])


def cancel(campaign):
    """Stop a campaign that hasn't finished. Mail already queued but not yet
    sent is withdrawn; what's already out stays out."""
    if campaign.status not in (Status.DRAFT, Status.QUEUED, Status.SENDING):
        raise CampaignError(_("This campaign has already finished."))
    with transaction.atomic():
        campaign.status = Status.CANCELLED
        campaign.save(update_fields=["status"])
        EmailMessage.objects.filter(campaign=campaign, status=EmailMessage.Status.PENDING).update(
            status=EmailMessage.Status.SUPPRESSED,
            status_reason="The campaign was cancelled.",
        )


def send_test(campaign, user):
    """The campaign's mail to its author, now, in their own language."""
    template_key, context = _mail(campaign, user)
    if not EmailTemplate.objects.filter(key=template_key).exists():
        raise CampaignError(_("There's no template “%(template_key)s”.") % {"template_key": template_key})
    if not user.email:
        raise CampaignError(_("Your account has no email address to send the test to."))
    return send(user, campaign.category, template_key, context, campaign=campaign, test=True, **_send_kwargs(campaign))


def queue_mail(campaign_id):
    """Queue the campaign's mail: the launch_campaign task. Returns how many
    new mails were queued."""
    lock = f"mailing:campaign-launch:{campaign_id}"
    if not cache.add(lock, 1, LAUNCH_LOCK_SECONDS):
        return 0  # another run is busy with it
    try:
        claimed = Campaign.objects.filter(pk=campaign_id, status=Status.QUEUED).update(status=Status.SENDING)
        campaign = Campaign.objects.get(pk=campaign_id)
        if not claimed and campaign.status != Status.SENDING:
            return 0
        queued = 0
        send_after = (
            campaign.scheduled_at if campaign.scheduled_at and campaign.scheduled_at > timezone.now() else None
        )
        for user in audience(campaign).order_by("pk").iterator(chunk_size=500):
            if Campaign.objects.filter(pk=campaign_id, status=Status.CANCELLED).exists():
                return queued
            key = f"campaign:{campaign.pk}:{user.pk}"
            if EmailMessage.objects.filter(idempotency_key=key).exists():
                continue
            template_key, context = _mail(campaign, user)
            send(
                user,
                campaign.category,
                template_key,
                context,
                campaign=campaign,
                idempotency_key=key,
                send_after=send_after,
                **_send_kwargs(campaign),
            )
            queued += 1
        Campaign.objects.filter(pk=campaign_id, status=Status.SENDING).update(queued_at=timezone.now())
        return queued
    finally:
        cache.delete(lock)


def launch_due(now=None):
    """Beat, every minute: start what's due, resume what was interrupted,
    complete what's done. Returns the ids handed to launch_campaign."""
    from .tasks import launch_campaign

    now = now or timezone.now()
    due = (
        list(Campaign.objects.filter(status=Status.QUEUED, scheduled_at__isnull=True).values_list("pk", flat=True))
        + list(Campaign.objects.filter(status=Status.QUEUED, scheduled_at__lte=now).values_list("pk", flat=True))
        + list(Campaign.objects.filter(status=Status.SENDING, queued_at__isnull=True).values_list("pk", flat=True))
    )
    for campaign_id in due:
        launch_campaign.delay(campaign_id)

    open_statuses = [EmailMessage.Status.PENDING, EmailMessage.Status.SENDING]
    for campaign in Campaign.objects.filter(status=Status.SENDING, queued_at__isnull=False):
        if not campaign.emailmessage_set.filter(status__in=open_statuses, is_test=False).exists():
            Campaign.objects.filter(pk=campaign.pk, status=Status.SENDING).update(status=Status.COMPLETED)
    return due


def stats(campaign):
    """The numbers for the campaign's page."""
    counts = dict(campaign.emailmessage_set.filter(is_test=False).values_list("status").annotate(n=Count("id")))
    result = {status: counts.get(status, 0) for status in EmailMessage.Status.values}
    result["queued"] = sum(counts.values())
    has_audience = campaign.segment_id or campaign.segment_snapshot or campaign.is_dojo_mailing
    result["audience"] = audience(campaign).count() if has_audience else 0
    if campaign.launched_at:
        recipients = campaign.emailmessage_set.filter(is_test=False).values("user_id")
        result["unsubscribed"] = (
            ConsentEvent.objects.filter(
                user_id__in=recipients,
                category=campaign.category,
                subscribed=False,
                created_at__gte=campaign.launched_at,
            )
            # A dojo mailing: stopping every dojo's news, or this dojo's.
            .filter(Q(dojo__isnull=True) | Q(dojo=campaign.dojo_id))
            .values("user_id")
            .distinct()
            .count()
        )
    else:
        result["unsubscribed"] = 0
    result["rate_limit"] = settings.MAILING_BATCH_RATE_LIMIT
    return result
