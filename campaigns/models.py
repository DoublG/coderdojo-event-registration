"""Campaigns, segments and journeys (DATA_MODEL.md §11): who the
organisation's and the dojos' mailings go to and what they send. Moved here
from mailing on 2 October 2026 with their tables, so the mail engine (the
mailing app) never depends on them (CODING_STANDARDS.md, "Layers")."""

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import gettext_lazy as _

from core.content_languages import TranslatableModel
from mailing.categories import MailCategory


class Segment(models.Model):
    """A campaign audience, described as rules rather than a list: resolved
    to accounts by mailing.segmentation.resolver.SegmentResolver when used.
    Its root groups (parent empty) are ANDed."""

    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)

    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "mailing_segment"  # moved from mailing, the table kept its name

    def __str__(self):
        return self.name


class SegmentGroupManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().select_related("segment")


class SegmentGroup(models.Model):
    """Combines its rules and child groups with AND or OR.

    `scope` says what the rules describe. In a `ninja` group every rule is
    about the *same child* ("a girl who attended event X"), and the group
    selects that child's guardians. A `user` group filters accounts
    directly. A ninja group can only contain ninja groups."""

    class Operator(models.TextChoices):
        AND = "and", _("AND")
        OR = "or", _("OR")

    class Scope(models.TextChoices):
        USER = "user", _("Accounts")
        NINJA = "ninja", _("Parents of a child who …")

    segment = models.ForeignKey(
        Segment,
        on_delete=models.CASCADE,
        related_name="groups",
    )

    parent = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="children",
    )

    operator = models.CharField(
        max_length=3,
        choices=Operator.choices,
        default=Operator.AND,
    )
    scope = models.CharField(max_length=5, choices=Scope.choices, default=Scope.USER)

    objects = SegmentGroupManager()

    class Meta:
        db_table = "mailing_segmentgroup"  # moved from mailing, the table kept its name

    def __str__(self):
        return f"{self.segment} ({self.get_scope_display()}, {self.operator})"

    def clean(self):
        if self.parent_id and self.parent.scope == self.Scope.NINJA and self.scope != self.Scope.NINJA:
            raise ValidationError({"scope": "A group inside a child group must also be about the child."})
        if self.parent_id and self.parent.segment_id != self.segment_id:
            raise ValidationError({"parent": "The parent group belongs to another segment."})


class SegmentRule(models.Model):
    """One condition: an attribute from mailing.segmentation.registry, an
    operator it supports and a JSON value."""

    group = models.ForeignKey(
        SegmentGroup,
        on_delete=models.CASCADE,
        related_name="rules",
    )

    attribute = models.CharField(max_length=100)
    operator = models.CharField(max_length=50)

    value = models.JSONField()

    class Meta:
        db_table = "mailing_segmentrule"  # moved from mailing, the table kept its name

    def __str__(self):
        return f"{self.attribute} {self.operator} {self.value}"

    def clean(self):
        from campaigns.segmentation.registry import get_attribute

        try:
            attribute = get_attribute(self.attribute)
        except ValueError as error:
            raise ValidationError({"attribute": str(error)}) from error
        if self.group_id and attribute.scope != self.group.scope:
            raise ValidationError(
                {
                    "attribute": f"“{attribute.label}” can't be used in a group about "
                    f"{self.group.get_scope_display().lower()}."
                }
            )
        try:
            attribute.validate(self.operator, self.value)
        except ValueError as error:
            raise ValidationError(str(error)) from error


class Campaign(TranslatableModel):
    """One mailing to a segment's audience. The organisation's admin role
    creates campaigns (DATA_MODEL.md §11, decisions); a dojo's champion
    writes a dojo mailing (`dojo` set, DATA_MODEL.md §25): always
    `dojo_news`, to one of the prepared audiences (mailing.dojo_audiences),
    with the dojo's own text in its languages, sent with the `dojo_message`
    template."""

    TRANSLATABLE_FIELDS = ("subject", "message")

    class Status(models.TextChoices):
        DRAFT = "draft"
        QUEUED = "queued"
        SENDING = "sending"
        COMPLETED = "completed"
        CANCELLED = "cancelled"

    # Optional reference to the segment used to create it.
    segment = models.ForeignKey(
        Segment,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )

    # Immutable copy of the segment definition at launch; empty while a draft.
    segment_snapshot = models.JSONField(null=True, blank=True)

    # A dojo mailing (DATA_MODEL.md §25); empty for the organisation's campaigns.
    dojo = models.ForeignKey("dojos.Dojo", null=True, blank=True, on_delete=models.CASCADE, related_name="mailings")
    audience = models.CharField(
        max_length=30, blank=True, help_text="A dojo mailing's audience (mailing.dojo_audiences)."
    )
    audience_params = models.JSONField(default=dict, blank=True)
    subject = models.CharField(max_length=150, blank=True, help_text="A dojo mailing's subject, main language.")
    message = models.TextField(blank=True, help_text="A dojo mailing's text (plain text), main language.")
    created_by = models.ForeignKey("accounts.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")

    name = models.CharField(max_length=200)

    category = models.CharField(max_length=20, choices=MailCategory.choices, default=MailCategory.NEWSLETTER)
    template_key = models.CharField(
        max_length=100, help_text="EmailTemplate.key; each recipient gets the version in their language."
    )
    context = models.JSONField(
        default=dict,
        blank=True,
        help_text='Extra template variables for this campaign, e.g. {"signup_url": "https://…"}.',
    )

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.DRAFT,
    )

    created_at = models.DateTimeField(auto_now_add=True)
    scheduled_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Leave empty to send as soon as it's launched.",
    )
    # Set by mailing.campaigns.launch / the launch_campaign task.
    launched_at = models.DateTimeField(null=True, blank=True, editable=False)
    launched_by = models.ForeignKey(
        "accounts.User",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        editable=False,
        related_name="+",
    )
    queued_at = models.DateTimeField(
        null=True,
        blank=True,
        editable=False,
        help_text="When every recipient's mail was queued.",
    )
    # mailing.campaigns.queue_chunk: the mail is queued in chunks, in account
    # id order, and this is the last account id done (0 = none yet).
    queued_up_to = models.PositiveBigIntegerField(
        default=0,
        editable=False,
        help_text="The last account id whose mail is queued (the mail is queued in chunks, in id order).",
    )

    class Meta:
        db_table = "mailing_campaign"  # moved from mailing, the table kept its name

    def __str__(self):
        return self.name

    @property
    def is_editable(self):
        return self.status == self.Status.DRAFT

    @property
    def is_dojo_mailing(self):
        return self.dojo_id is not None

    def content_languages(self):
        return self.dojo.content_languages() if self.dojo_id else [settings.LANGUAGE_CODE]


class Journey(models.Model):
    """A standing campaign (DATA_MODEL.md §11, Tier 3): every day, everyone
    who newly matches its segment gets its mail, at most once per
    `cooldown_days`. E.g. "we miss you" when a child becomes at risk. Run by
    mailing.journeys.run (beat, daily); managed in the organisation
    dashboard."""

    name = models.CharField(max_length=200)
    segment = models.ForeignKey(Segment, null=True, blank=True, on_delete=models.SET_NULL, related_name="journeys")
    category = models.CharField(max_length=20, choices=MailCategory.choices, default=MailCategory.DOJO_NEWS)
    template_key = models.CharField(max_length=100)
    context = models.JSONField(default=dict, blank=True)
    cooldown_days = models.PositiveIntegerField(
        default=365,
        help_text="Someone who got it doesn't get it again for this many days.",
    )
    is_active = models.BooleanField(default=False)
    activated_at = models.DateTimeField(null=True, blank=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "mailing_journey"  # moved from mailing, the table kept its name

    def __str__(self):
        return self.name


class JourneyDeliveryManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().select_related("journey", "user")


class JourneyDelivery(models.Model):
    """One journey mail to one account: what the cool-down is checked against."""

    journey = models.ForeignKey(Journey, on_delete=models.CASCADE, related_name="deliveries")
    user = models.ForeignKey("accounts.User", on_delete=models.CASCADE, related_name="+")
    email = models.ForeignKey(
        "mailing.EmailMessage", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    objects = JourneyDeliveryManager()

    class Meta:
        db_table = "mailing_journeydelivery"  # moved from mailing, the table kept its name
        indexes = [models.Index(fields=["journey", "user", "created_at"], name="mailing_journey_delivery_idx")]

    def __str__(self):
        return f"{self.journey} → {self.user}"
