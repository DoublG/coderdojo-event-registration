"""The organisation's management dashboard for mail (/manage/…, shell
core/_manage_base.html): campaigns, journeys, segments, mail templates and the mail queue. Only the Communication area gets in
(accounts.organisation.require_area, the admin role, DATA_MODEL.md §23);
every campaign change goes through mailing.campaigns."""

from datetime import timedelta

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db.models import Min, Q
from django.db.models.functions import Coalesce
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from accounts.organisation import Area, require_area

from . import campaigns, journeys
from .forms import CampaignForm, JourneyForm, NewTemplateForm, SegmentForm, TemplateVersionForm
from .models import (
    BounceRecord,
    Campaign,
    EmailMessage,
    EmailSuppression,
    EmailTemplate,
    Journey,
    Segment,
    SegmentGroup,
    SegmentRule,
)
from .rendering import FALLBACK_LANGUAGE
from .rendering import render as render_template
from .seed_templates import GENERIC_SAMPLE_CONTEXT, SAMPLE_CONTEXT, SYSTEM_TEMPLATE_KEYS
from .segmentation.base import OPERATOR_LABELS
from .segmentation.registry import get_attribute, get_attributes
from .segmentation.resolver import SegmentResolver

AUDIENCE_SAMPLE = 10


@login_required
def campaign_list(request):
    require_area(request, Area.COMMUNICATION)
    rows = [(c, campaigns.stats(c)) for c in Campaign.objects.select_related("segment").order_by("-created_at")]
    return render(request, "mailing/manage/campaign_list.html", {"rows": rows, "active": "campaigns"})


@login_required
def campaign_create(request):
    require_area(request, Area.COMMUNICATION)
    form = CampaignForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        campaign = form.save()
        messages.success(request, _("Campaign saved as a draft."))
        return redirect("manage_campaign_detail", campaign_id=campaign.pk)
    return render(request, "mailing/manage/campaign_form.html", {"form": form, "active": "campaigns"})


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
    campaign = get_object_or_404(Campaign.objects.select_related("segment", "launched_by"), pk=campaign_id)
    form = None
    if campaign.is_editable:
        form = CampaignForm(request.POST or None, instance=campaign)
        if request.method == "POST" and form.is_valid():
            form.save()
            messages.success(request, _("Campaign saved."))
            return redirect("manage_campaign_detail", campaign_id=campaign.pk)
    audience = campaigns.audience(campaign)
    return render(
        request,
        "mailing/manage/campaign_detail.html",
        {
            "campaign": campaign,
            "form": form,
            "active": "campaigns",
            "stats": campaigns.stats(campaign),
            "audience_sample": audience.order_by("pk")[:AUDIENCE_SAMPLE],
            "problems": campaigns.launch_problems(campaign) if campaign.is_editable else [],
            "previews": _previews(campaign, request.user),
        },
    )


def _campaign_action(request, campaign_id, action, success):
    require_area(request, Area.COMMUNICATION)
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
    return _campaign_action(request, campaign_id, campaigns.cancel, lambda c: "Campaign cancelled.")


@login_required
def segment_list(request):
    require_area(request, Area.COMMUNICATION)
    resolver = SegmentResolver()
    rows = [(s, resolver.resolve(s).count()) for s in Segment.objects.order_by("name")]
    return render(request, "mailing/manage/segment_list.html", {"rows": rows, "active": "segments"})


# --- the segment builder -----------------------------------------------------------


def _tree(segment):
    """The segment's groups as nested dicts for the template: each with its
    rules described in words and its child groups."""
    groups = list(segment.groups.prefetch_related("rules").order_by("id"))
    children = {}
    for group in groups:
        children.setdefault(group.parent_id, []).append(group)

    def node(group):
        rules = []
        for rule in sorted(group.rules.all(), key=lambda r: r.pk):
            try:
                text = get_attribute(rule.attribute).describe(rule.operator, rule.value)
            except (ValueError, KeyError, TypeError):
                text = f"{rule.attribute} {rule.operator} {rule.value} (not understood)"
            rules.append({"rule": rule, "text": text})
        return {"group": group, "rules": rules, "children": [node(child) for child in children.get(group.pk, [])]}

    return [node(root) for root in children.get(None, [])]


def _attributes_for(scope):
    return [a for a in get_attributes() if a.scope == scope and a.in_builder]


@login_required
def segment_create(request):
    require_area(request, Area.COMMUNICATION)
    form = SegmentForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        segment = form.save()
        messages.success(request, _("Segment created. Now add who's in it."))
        return redirect("manage_segment_detail", segment_id=segment.pk)
    return render(request, "mailing/manage/segment_form.html", {"form": form, "active": "segments"})


@login_required
def segment_detail(request, segment_id):
    require_area(request, Area.COMMUNICATION)
    segment = get_object_or_404(Segment, pk=segment_id)
    form = SegmentForm(request.POST or None, instance=segment)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, _("Segment saved."))
        return redirect("manage_segment_detail", segment_id=segment.pk)
    accounts = SegmentResolver().resolve(segment)
    return render(
        request,
        "mailing/manage/segment_detail.html",
        {
            "segment": segment,
            "form": form,
            "tree": _tree(segment),
            "active": "segments",
            "count": accounts.count(),
            "sample": accounts.order_by("pk")[:AUDIENCE_SAMPLE],
            "user_attributes": _attributes_for("user"),
            "ninja_attributes": _attributes_for("ninja"),
            "scopes": SegmentGroup.Scope.choices,
            "operators": SegmentGroup.Operator.choices,
            "draft_campaigns": segment.campaign_set.filter(status=Campaign.Status.DRAFT),
        },
    )


def _back(segment, message=None, request=None, error=False):
    if message:
        (messages.error if error else messages.success)(request, message)
    return redirect("manage_segment_detail", segment_id=segment.pk)


def _validation_text(error):
    return (
        " ".join(m for messages_ in error.message_dict.values() for m in messages_)
        if hasattr(error, "message_dict")
        else " ".join(error.messages)
    )


@login_required
@require_POST
def segment_add_group(request, segment_id):
    require_area(request, Area.COMMUNICATION)
    segment = get_object_or_404(Segment, pk=segment_id)
    parent = (
        get_object_or_404(SegmentGroup, pk=request.POST["parent"], segment=segment)
        if request.POST.get("parent")
        else None
    )
    group = SegmentGroup(
        segment=segment,
        parent=parent,
        scope=request.POST.get("scope", "user"),
        operator=request.POST.get("operator", SegmentGroup.Operator.AND),
    )
    try:
        group.full_clean()
    except ValidationError as error:
        return _back(segment, _validation_text(error), request, error=True)
    group.save()
    return _back(segment)


@login_required
@require_POST
def segment_update_group(request, segment_id, group_id):
    require_area(request, Area.COMMUNICATION)
    group = get_object_or_404(SegmentGroup, pk=group_id, segment_id=segment_id)
    if request.POST.get("operator") in SegmentGroup.Operator.values:
        group.operator = request.POST["operator"]
        group.save(update_fields=["operator"])
    return _back(group.segment)


@login_required
@require_POST
def segment_delete_group(request, segment_id, group_id):
    require_area(request, Area.COMMUNICATION)
    group = get_object_or_404(SegmentGroup, pk=group_id, segment_id=segment_id)
    segment = group.segment
    group.delete()  # its rules and child groups go with it
    return _back(segment, "Group removed.", request)


@login_required
def segment_rule_fields(request, segment_id, group_id):
    """htmx: the operator and value fields for the attribute just picked."""
    require_area(request, Area.COMMUNICATION)
    group = get_object_or_404(SegmentGroup, pk=group_id, segment_id=segment_id)
    try:
        attribute = get_attribute(request.GET.get("attribute", ""))
    except ValueError:
        attribute = None
    return render(
        request,
        "mailing/manage/_rule_fields.html",
        {
            "group": group,
            "attribute": attribute,
            "operators": [(op, OPERATOR_LABELS.get(op, op)) for op in attribute.operators] if attribute else [],
            "choices": attribute.choices() if attribute else [],
        },
    )


@login_required
@require_POST
def segment_add_rule(request, segment_id, group_id):
    require_area(request, Area.COMMUNICATION)
    group = get_object_or_404(SegmentGroup, pk=group_id, segment_id=segment_id)
    try:
        attribute = get_attribute(request.POST.get("attribute", ""))
    except ValueError:
        return _back(group.segment, "Pick what the rule is about.", request, error=True)
    operator = request.POST.get("operator", attribute.operators[0])
    rule = SegmentRule(
        group=group,
        attribute=attribute.key,
        operator=operator,
        value=attribute.value_from_form(operator, request.POST),
    )
    try:
        rule.full_clean()
    except ValidationError as error:
        return _back(group.segment, _validation_text(error), request, error=True)
    rule.save()
    return _back(group.segment, f"Added: {attribute.describe(operator, rule.value)}.", request)


@login_required
@require_POST
def segment_delete_rule(request, segment_id, rule_id):
    require_area(request, Area.COMMUNICATION)
    rule = get_object_or_404(SegmentRule, pk=rule_id, group__segment_id=segment_id)
    segment = rule.group.segment
    rule.delete()
    return _back(segment, "Rule removed.", request)


@login_required
@require_POST
def segment_delete(request, segment_id):
    require_area(request, Area.COMMUNICATION)
    segment = get_object_or_404(Segment, pk=segment_id)
    segment.delete()  # launched campaigns keep their frozen copy
    messages.success(request, _("Segment “%(segment)s” deleted.") % {"segment": segment.name})
    return redirect("manage_segment_list")


# --- mail templates -------------------------------------------------------------------


def _sample_context(key):
    return {**GENERIC_SAMPLE_CONTEXT, **SAMPLE_CONTEXT.get(key, {})}


@login_required
def template_list(request):
    require_area(request, Area.COMMUNICATION)
    languages = dict(settings.LANGUAGES)
    rows = {}
    for template in EmailTemplate.objects.order_by("key", "language"):
        row = rows.setdefault(
            template.key,
            {
                "key": template.key,
                "category": template.get_category_display(),
                "description": template.description,
                "languages": [],
            },
        )
        row["languages"].append(languages.get(template.language, template.language))
    used_by = {}
    for campaign in Campaign.objects.exclude(status=Campaign.Status.CANCELLED).only("name", "template_key"):
        used_by.setdefault(campaign.template_key, []).append(campaign.name)
    for key, row in rows.items():
        row["system"] = key in SYSTEM_TEMPLATE_KEYS
        row["campaigns"] = used_by.get(key, [])
    return render(request, "mailing/manage/template_list.html", {"rows": rows.values(), "active": "templates"})


@login_required
def template_create(request):
    require_area(request, Area.COMMUNICATION)
    form = NewTemplateForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        EmailTemplate.objects.create(
            key=form.cleaned_data["key"],
            language=FALLBACK_LANGUAGE,
            category=form.cleaned_data["category"],
            description=form.cleaned_data["description"],
            subject="{{ recipient_name }}, ...",
            body="Hi {{ recipient_name }},\n\n...\n\nThe CoderDojo Belgium team\n\n--\n"
            "You get this mail because of your mail preferences. Unsubscribe: {{ unsubscribe_url }}",
        )
        messages.success(
            request,
            _(
                "Template created. Write the English version first: it's used for every language that has no version of its own."
            ),
        )
        return redirect("manage_template_edit", key=form.cleaned_data["key"], language=FALLBACK_LANGUAGE)
    return render(request, "mailing/manage/template_new.html", {"form": form, "active": "templates"})


@login_required
def template_edit(request, key, language):
    require_area(request, Area.COMMUNICATION)
    languages = dict(settings.LANGUAGES)
    if language not in languages:
        raise Http404
    versions = {t.language: t for t in EmailTemplate.objects.filter(key=key)}
    if not versions:
        raise Http404
    english = versions.get(FALLBACK_LANGUAGE) or next(iter(versions.values()))
    template = versions.get(language) or EmailTemplate(
        key=key,
        language=language,
        category=english.category,
        description=english.description,
        subject=english.subject,
        body=english.body,
    )
    sample = _sample_context(key)
    form = TemplateVersionForm(request.POST or None, instance=template, sample_context=sample)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, _("%(language)s version saved.") % {"language": languages[language]})
        return redirect("manage_template_edit", key=key, language=language)
    preview = None
    if template.pk and not form.errors:
        preview = render_template(key, language, sample)
    return render(
        request,
        "mailing/manage/template_edit.html",
        {
            "form": form,
            "key": key,
            "language": language,
            "language_name": languages[language],
            "tabs": [(code, name, code in versions) for code, name in settings.LANGUAGES],
            "is_new_version": template.pk is None,
            "preview": preview,
            "category": english.get_category_display(),
            "system": key in SYSTEM_TEMPLATE_KEYS,
            "fallback": FALLBACK_LANGUAGE,
            "sample_names": sorted(sample),
            "active": "templates",
        },
    )


@login_required
@require_POST
def template_delete(request, key, language=None):
    """Delete one language version, or (language empty) a whole campaign
    template. The site's own templates, and the English fallback of any
    template, stay; so does a template a draft campaign still uses."""
    require_area(request, Area.COMMUNICATION)
    versions = EmailTemplate.objects.filter(key=key)
    if not versions.exists():
        raise Http404
    in_use = Campaign.objects.filter(template_key=key, status__in=[Campaign.Status.DRAFT, Campaign.Status.QUEUED])
    if language:
        if language == FALLBACK_LANGUAGE:
            messages.error(request, _("The English version is the fallback for every language: it can't be deleted."))
        else:
            versions.filter(language=language).delete()
            messages.success(request, _("That language version is deleted; English is used instead."))
        return redirect("manage_template_edit", key=key, language=FALLBACK_LANGUAGE)
    if key in SYSTEM_TEMPLATE_KEYS:
        messages.error(request, _("The site sends this template itself: it can be edited, not deleted."))
    elif in_use.exists():
        messages.error(request, _("A campaign that hasn't gone out yet uses this template."))
    else:
        versions.delete()
        messages.success(request, _("Template “%(key)s” deleted.") % {"key": key})
        return redirect("manage_template_list")
    return redirect("manage_template_edit", key=key, language=FALLBACK_LANGUAGE)


# --- journeys ---------------------------------------------------------------------------


@login_required
def journey_list(request):
    require_area(request, Area.COMMUNICATION)
    rows = [(j, journeys.stats(j)) for j in Journey.objects.select_related("segment").order_by("name")]
    return render(request, "mailing/manage/journey_list.html", {"rows": rows, "active": "journeys"})


@login_required
def journey_create(request):
    require_area(request, Area.COMMUNICATION)
    form = JourneyForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        journey = form.save()
        messages.success(request, _("Journey saved. It's paused until you activate it."))
        return redirect("manage_journey_detail", journey_id=journey.pk)
    return render(request, "mailing/manage/journey_form.html", {"form": form, "active": "journeys"})


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
        "mailing/manage/journey_detail.html",
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


# --- the mail queue: what's waiting, what failed, bounces and blocked addresses ---

MAIL_QUEUE_LIMIT = 50  # rows per section
MAIL_QUEUE_RECENT_DAYS = 30  # how far back failures and bounces are shown
# Mail due longer than this and still waiting means the workers aren't sending
# (the same threshold as requeue_stuck_emails' warning in the log).
MAIL_QUEUE_STALLED_AFTER = timedelta(minutes=30)


@login_required
def mail_queue(request):
    """The mail queue at a glance (read-only): mail waiting to go out, mail
    that failed, bounces and complaints read from the bounce mailbox, and
    the addresses nothing is sent to any more. Fixing things (retrying a
    mail, unblocking an address) stays in the Django admin."""
    require_area(request, Area.COMMUNICATION)
    now = timezone.now()
    since = now - timedelta(days=MAIL_QUEUE_RECENT_DAYS)
    Status = EmailMessage.Status
    query = request.GET.get("q", "").strip()

    mail = EmailMessage.objects.select_related("campaign")
    bounces = BounceRecord.objects.select_related("message")
    blocked = EmailSuppression.objects.all()
    if query:
        mail = mail.filter(Q(recipient__icontains=query) | Q(user__email__icontains=query))
        bounces = bounces.filter(email__icontains=query)
        blocked = blocked.filter(email__icontains=query)

    due = Q(send_after__isnull=True) | Q(send_after__lte=now)
    oldest_due = (
        EmailMessage.objects.filter(due, status=Status.PENDING)
        .annotate(due_at=Coalesce("send_after", "created_at"))
        .aggregate(oldest=Min("due_at"))["oldest"]
    )
    waiting = mail.filter(status__in=[Status.PENDING, Status.SENDING])
    failed = mail.filter(status=Status.FAILED, created_at__gte=since)
    recent_bounces = bounces.filter(created_at__gte=since)
    counts = {
        "pending": EmailMessage.objects.filter(due, status=Status.PENDING).count(),
        "scheduled": EmailMessage.objects.filter(status=Status.PENDING, send_after__gt=now).count(),
        "sending": EmailMessage.objects.filter(status=Status.SENDING).count(),
        "sent_today": EmailMessage.objects.filter(status=Status.SENT, sent_at__gte=now - timedelta(days=1)).count(),
        "failed": EmailMessage.objects.filter(status=Status.FAILED, created_at__gte=since).count(),
        "bounces": BounceRecord.objects.filter(created_at__gte=since).count(),
        "blocked": EmailSuppression.objects.count(),
    }
    return render(
        request,
        "mailing/manage/mail_queue.html",
        {
            "active": "mail_queue",
            "query": query,
            "counts": counts,
            "recent_days": MAIL_QUEUE_RECENT_DAYS,
            "limit": MAIL_QUEUE_LIMIT,
            "oldest_due": oldest_due,
            "stalled": bool(oldest_due and now - oldest_due > MAIL_QUEUE_STALLED_AFTER),
            "bounce_mailbox_on": bool(settings.MAILING_BOUNCE_IMAP_HOST),
            "waiting": waiting.order_by("priority", "created_at")[:MAIL_QUEUE_LIMIT],
            "failed": failed.order_by("-created_at")[:MAIL_QUEUE_LIMIT],
            "bounces": recent_bounces[:MAIL_QUEUE_LIMIT],
            "blocked": blocked.order_by("-created_at")[:MAIL_QUEUE_LIMIT],
        },
    )
