from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from .categories import MailCategory


class Segment(models.Model):
    """A campaign audience, described as rules rather than a list: resolved
    to accounts by mailing.segmentation.resolver.SegmentResolver when used.
    Its root groups (parent empty) are ANDed."""

    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)

    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

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
        AND = "and", "AND"
        OR = "or", "OR"

    class Scope(models.TextChoices):
        USER = "user", "Accounts"
        NINJA = "ninja", "Parents of a child who …"

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

    def __str__(self):
        return f"{self.attribute} {self.operator} {self.value}"

    def clean(self):
        from .segmentation.registry import get_attribute

        try:
            attribute = get_attribute(self.attribute)
        except ValueError as error:
            raise ValidationError({"attribute": str(error)}) from error
        if self.group_id and attribute.scope != self.group.scope:
            raise ValidationError({"attribute": f"“{attribute.label}” can't be used in a group about "
                                                f"{self.group.get_scope_display().lower()}."})
        try:
            attribute.validate(self.operator, self.value)
        except ValueError as error:
            raise ValidationError(str(error)) from error


class Campaign(models.Model):
    """One mailing to a segment's audience. Only the organisation's admin
    role creates campaigns (DATA_MODEL.md §11, decisions)."""

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

    name = models.CharField(max_length=200)

    category = models.CharField(max_length=20, choices=MailCategory.choices, default=MailCategory.NEWSLETTER)
    template_key = models.CharField(
        max_length=100, help_text="EmailTemplate.key; each recipient gets the version in their language."
    )
    context = models.JSONField(
        default=dict, blank=True,
        help_text="Extra template variables for this campaign, e.g. {\"signup_url\": \"https://…\"}.",
    )

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.DRAFT,
    )

    created_at = models.DateTimeField(auto_now_add=True)
    scheduled_at = models.DateTimeField(
        null=True, blank=True, help_text="Leave empty to send as soon as it's launched.",
    )
    # Set by mailing.campaigns.launch / the launch_campaign task.
    launched_at = models.DateTimeField(null=True, blank=True, editable=False)
    launched_by = models.ForeignKey(
        "accounts.User", null=True, blank=True, on_delete=models.SET_NULL, editable=False, related_name="+",
    )
    queued_at = models.DateTimeField(
        null=True, blank=True, editable=False, help_text="When every recipient's mail was queued.",
    )

    def __str__(self):
        return self.name

    @property
    def is_editable(self):
        return self.status == self.Status.DRAFT


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
        default=365, help_text="Someone who got it doesn't get it again for this many days.",
    )
    is_active = models.BooleanField(default=False)
    activated_at = models.DateTimeField(null=True, blank=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class JourneyDeliveryManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().select_related("journey", "user")


class JourneyDelivery(models.Model):
    """One journey mail to one account: what the cool-down is checked against."""

    journey = models.ForeignKey(Journey, on_delete=models.CASCADE, related_name="deliveries")
    user = models.ForeignKey("accounts.User", on_delete=models.CASCADE, related_name="+")
    email = models.ForeignKey("EmailMessage", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    objects = JourneyDeliveryManager()

    class Meta:
        indexes = [models.Index(fields=["journey", "user", "created_at"], name="mailing_journey_delivery_idx")]

    def __str__(self):
        return f"{self.journey} → {self.user}"


class EmailTemplate(models.Model):
    """Subject and plain-text body in Django template syntax, one row per
    key and language. Rendered by mailing.rendering.render(), which falls
    back to MAILING_FALLBACK_LANGUAGE when a language is missing."""

    key = models.CharField(max_length=100)
    language = models.CharField(max_length=10, choices=settings.LANGUAGES)
    category = models.CharField(max_length=20, choices=MailCategory.choices)
    description = models.CharField(
        max_length=255, blank=True, help_text="When it's sent and which variables it uses."
    )
    subject = models.CharField(max_length=255)
    body = models.TextField()

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["key", "language"], name="unique_email_template_language"),
        ]
        ordering = ["key", "language"]

    def __str__(self):
        return f"{self.key} [{self.language}]"

class EmailMessageManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().select_related("user")


class EmailMessage(models.Model):
    """One mail to one recipient, and the queue it waits in: every mail is
    a row first (mailing.services.send), and the Celery dispatcher claims
    `pending` rows and sends them (DATA_MODEL.md §11, "Sending pipeline").
    Subject and body are rendered when the row is created, so the row is
    also the record of exactly what was sent."""

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        SENDING = "sending", "Sending"
        SENT = "sent", "Sent"
        FAILED = "failed", "Failed"
        BOUNCED = "bounced", "Bounced"
        SUPPRESSED = "suppressed", "Not sent (no consent, no address or blocked)"

    category = models.CharField(max_length=20, choices=MailCategory.choices)
    template_key = models.CharField(max_length=100, blank=True)
    user = models.ForeignKey(
        "accounts.User",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )
    recipient = models.EmailField(blank=True, help_text="The address used, as it was at the time.")
    language = models.CharField(max_length=10, blank=True)
    subject = models.CharField(max_length=255)
    body = models.TextField()
    campaign = models.ForeignKey(Campaign, null=True, blank=True, on_delete=models.SET_NULL)

    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    status_reason = models.CharField(max_length=255, blank=True, help_text="Why it was suppressed or failed.")
    priority = models.PositiveSmallIntegerField(default=5, help_text="Lower is sent first.")
    send_after = models.DateTimeField(null=True, blank=True, help_text="Not sent before this time.")
    claimed_at = models.DateTimeField(null=True, blank=True)
    attempts = models.PositiveSmallIntegerField(default=0)
    # Makes a send() idempotent: a second send() with the same key is a no-op
    # (e.g. "reminder:event42:ninja7"). Null for mail that can repeat.
    idempotency_key = models.CharField(max_length=200, null=True, blank=True, unique=True)
    message_id = models.CharField(max_length=255, blank=True, db_index=True, help_text="Our Message-ID header.")
    is_test = models.BooleanField(
        default=False, help_text="A campaign test sent to its author: preferences don't apply (blocks still do).",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    bounced_at = models.DateTimeField(null=True, blank=True)

    objects = EmailMessageManager()

    class Meta:
        indexes = [models.Index(fields=["status", "priority", "created_at"], name="mailing_queue_idx")]

    def __str__(self):
        return f"{self.recipient or self.user} — {self.subject}"


class MailPreferenceManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().select_related("user")


class MailPreference(models.Model):
    """An account's choice for one mail category. No row means the
    category's default (mailing.categories.DEFAULT_SUBSCRIBED). Changed only
    through mailing.preferences.set_preference, which also logs a
    ConsentEvent."""

    user = models.ForeignKey("accounts.User", on_delete=models.CASCADE, related_name="mail_preferences")
    category = models.CharField(max_length=20, choices=MailCategory.choices)
    subscribed = models.BooleanField()
    changed_at = models.DateTimeField(auto_now=True)

    objects = MailPreferenceManager()

    class Meta:
        constraints = [models.UniqueConstraint(fields=["user", "category"], name="unique_mail_preference")]

    def __str__(self):
        return f"{self.user}: {self.category} {'on' if self.subscribed else 'off'}"


class ConsentEventManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().select_related("user")


class ConsentEvent(models.Model):
    """Append-only log of every preference change, as proof of consent:
    who, what, when, how and under which wording. Nothing reads it to
    decide who gets mail; MailPreference is the current state."""

    SIGNUP = "signup"
    PREFERENCES = "preferences"
    UNSUBSCRIBE_LINK = "unsubscribe_link"
    ADMIN = "admin"
    BOUNCE = "bounce"
    SOURCE_CHOICES = [
        (SIGNUP, "Sign-up form"),
        (PREFERENCES, "Mail preferences page"),
        (UNSUBSCRIBE_LINK, "Unsubscribe link"),
        (ADMIN, "Admin"),
        (BOUNCE, "Bounce or complaint"),
    ]

    user = models.ForeignKey("accounts.User", on_delete=models.CASCADE, related_name="consent_events")
    category = models.CharField(max_length=20, choices=MailCategory.choices)
    subscribed = models.BooleanField()
    source = models.CharField(max_length=20, choices=SOURCE_CHOICES)
    wording_version = models.CharField(max_length=20, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = ConsentEventManager()

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.user}: {self.category} {'on' if self.subscribed else 'off'} ({self.source})"


class EmailSuppression(models.Model):
    """An address nothing is sent to any more, whatever the preferences:
    a hard bounce, a spam complaint, or blocked by hand."""

    HARD_BOUNCE = "hard_bounce"
    SOFT_BOUNCES = "soft_bounces"
    COMPLAINT = "complaint"
    MANUAL = "manual"
    REASON_CHOICES = [
        (HARD_BOUNCE, "Hard bounce"),
        (SOFT_BOUNCES, "Repeated soft bounces"),
        (COMPLAINT, "Spam complaint"),
        (MANUAL, "Blocked by hand"),
    ]

    email = models.EmailField(unique=True, help_text="Stored lower-case.")
    reason = models.CharField(max_length=20, choices=REASON_CHOICES)
    note = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.email} ({self.get_reason_display()})"

    def save(self, *args, **kwargs):
        self.email = self.email.strip().lower()
        super().save(*args, **kwargs)


class BounceRecord(models.Model):
    """One bounce or complaint read from the bounce mailbox (append-only):
    what came back, for which address and, when it could be matched, which
    mail. Soft bounces are counted from here."""

    HARD = "hard"
    SOFT = "soft"
    COMPLAINT = "complaint"
    KIND_CHOICES = [(HARD, "Hard bounce (5.x.x)"), (SOFT, "Soft bounce (4.x.x)"), (COMPLAINT, "Spam complaint")]

    email = models.EmailField(db_index=True, help_text="Stored lower-case.")
    kind = models.CharField(max_length=10, choices=KIND_CHOICES)
    status_code = models.CharField(max_length=20, blank=True, help_text="e.g. 5.1.1")
    diagnostic = models.CharField(max_length=255, blank=True)
    message = models.ForeignKey(EmailMessage, null=True, blank=True, on_delete=models.SET_NULL, related_name="bounces")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.email} ({self.kind} {self.status_code})"


class ProcessedImapMessage(models.Model):
    """A message in the bounce mailbox that process_bounces has handled, so
    it's never handled twice. `mailbox` is "<name>:<UIDVALIDITY>" for IMAP,
    or "pop3:<host>" (with the message's UIDL as `uid`) for POP3."""

    mailbox = models.CharField(max_length=255)
    uid = models.CharField(max_length=255)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["mailbox", "uid"],
                name="unique_processed_mail",
            )
        ]

    def __str__(self):
        return f"{self.mailbox} #{self.uid}"

