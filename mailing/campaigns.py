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
"""

from django.conf import settings
from django.core.cache import cache
from django.db import transaction
from django.db.models import Count
from django.utils import timezone

from .categories import CAN_OPT_OUT
from .models import Campaign, ConsentEvent, EmailMessage, EmailTemplate
from .preferences import subscribed_q
from .rendering import FALLBACK_LANGUAGE
from .segmentation.resolver import SegmentResolver, serialize_segment
from .services import send

Status = Campaign.Status
LAUNCH_LOCK_SECONDS = 30 * 60


class CampaignError(Exception):
    pass


def launch_problems(campaign):
    """What stops `campaign` from being launched, as readable sentences."""
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
    if campaign.segment_snapshot:
        accounts = resolver.resolve_definition(campaign.segment_snapshot)
    elif campaign.segment_id:
        accounts = resolver.resolve(campaign.segment)
    else:
        accounts = resolver.resolve_definition(None)  # nobody
    return accounts.filter(subscribed_q(campaign.category))


def launch(campaign, user):
    if problems := launch_problems(campaign):
        raise CampaignError(" ".join(problems))
    campaign.segment_snapshot = serialize_segment(campaign.segment)
    campaign.status = Status.QUEUED
    campaign.launched_at = timezone.now()
    campaign.launched_by = user
    campaign.save(update_fields=["segment_snapshot", "status", "launched_at", "launched_by"])


def cancel(campaign):
    """Stop a campaign that hasn't finished. Mail already queued but not yet
    sent is withdrawn; what's already out stays out."""
    if campaign.status not in (Status.DRAFT, Status.QUEUED, Status.SENDING):
        raise CampaignError("This campaign has already finished.")
    with transaction.atomic():
        campaign.status = Status.CANCELLED
        campaign.save(update_fields=["status"])
        EmailMessage.objects.filter(campaign=campaign, status=EmailMessage.Status.PENDING).update(
            status=EmailMessage.Status.SUPPRESSED, status_reason="The campaign was cancelled.",
        )


def send_test(campaign, user):
    """The campaign's mail to its author, now, in their own language."""
    if not EmailTemplate.objects.filter(key=campaign.template_key).exists():
        raise CampaignError(f"There's no template “{campaign.template_key}”.")
    if not user.email:
        raise CampaignError("Your account has no email address to send the test to.")
    return send(user, campaign.category, campaign.template_key, campaign.context, campaign=campaign, test=True)


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
        send_after = campaign.scheduled_at if campaign.scheduled_at and campaign.scheduled_at > timezone.now() else None
        for user in audience(campaign).order_by("pk").iterator(chunk_size=500):
            if Campaign.objects.filter(pk=campaign_id, status=Status.CANCELLED).exists():
                return queued
            key = f"campaign:{campaign.pk}:{user.pk}"
            if EmailMessage.objects.filter(idempotency_key=key).exists():
                continue
            send(user, campaign.category, campaign.template_key, campaign.context,
                 campaign=campaign, idempotency_key=key, send_after=send_after)
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
    due = list(
        Campaign.objects.filter(status=Status.QUEUED, scheduled_at__isnull=True).values_list("pk", flat=True)
    ) + list(
        Campaign.objects.filter(status=Status.QUEUED, scheduled_at__lte=now).values_list("pk", flat=True)
    ) + list(
        Campaign.objects.filter(status=Status.SENDING, queued_at__isnull=True).values_list("pk", flat=True)
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
    counts = dict(
        campaign.emailmessage_set.filter(is_test=False).values_list("status").annotate(n=Count("id"))
    )
    result = {status: counts.get(status, 0) for status in EmailMessage.Status.values}
    result["queued"] = sum(counts.values())
    result["audience"] = audience(campaign).count() if (campaign.segment_id or campaign.segment_snapshot) else 0
    if campaign.launched_at:
        recipients = campaign.emailmessage_set.filter(is_test=False).values("user_id")
        result["unsubscribed"] = ConsentEvent.objects.filter(
            user_id__in=recipients, category=campaign.category, subscribed=False,
            created_at__gte=campaign.launched_at,
        ).values("user_id").distinct().count()
    else:
        result["unsubscribed"] = 0
    result["rate_limit"] = settings.MAILING_BATCH_RATE_LIMIT
    return result
