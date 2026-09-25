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
    scheduled_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return self.name


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

class EmailType(models.TextChoices):
    TRANSACTIONAL = "transactional"
    REGISTRATION_REMINDER = "registration_reminder"
    WAITLIST = "waitlist"
    NEWSLETTER = "newsletter"

class EmailMessage(models.Model):
    class Type(models.TextChoices):
        TRANSACTIONAL = "transactional"
        REGISTRATION_REMINDER = "registration_reminder"
        WAITLIST = "waitlist"
        NEWSLETTER = "newsletter"

    type = models.CharField(max_length=50, choices=Type.choices)

    recipient = models.EmailField()
    user = models.ForeignKey(
        "accounts.User",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )

    subject = models.CharField(max_length=255)

    status = models.CharField(
        max_length=20,
        choices=[
            ("pending", "Pending"),
            ("sending", "Sending"),
            ("sent", "Sent"),
            ("failed", "Failed"),
            ("bounced", "Bounced"),
        ],
        default="pending",
    )

    provider_id = models.CharField(
        max_length=255,
        blank=True,
        null=True,
    )

    created_at = models.DateTimeField(auto_now_add=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    bounced_at = models.DateTimeField(null=True, blank=True)

    campaign = models.ForeignKey(Campaign,null=True,blank=True, on_delete=models.SET_NULL,)

class ProcessedImapMessage(models.Model):
    mailbox = models.CharField(max_length=255)
    uid = models.CharField(max_length=255)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["mailbox", "uid"],
                name="unique_processed_mail",
            )
        ]

