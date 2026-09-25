from django.db import models

class Segment(models.Model):
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)

    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

class SegmentRule(models.Model):
    segment = models.ForeignKey(
        Segment,
        on_delete=models.CASCADE,
        related_name="rules",
    )

    attribute = models.CharField(max_length=100)
    operator = models.CharField(max_length=50)

    value = models.JSONField()

class SegmentGroup(models.Model):

    def __str__(self):
        return f"{self.segment} ({self.operator})"

    class Operator(models.TextChoices):
        AND = "and", "AND"
        OR = "or", "OR"

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

class Campaign(models.Model):
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

    # Immutable copy of the segment definition at launch.
    segment_snapshot = models.JSONField()

    name = models.CharField(max_length=200)

    subject = models.CharField(max_length=255)
    email_type = models.CharField(max_length=50)

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.DRAFT,
    )

    created_at = models.DateTimeField(auto_now_add=True)
    scheduled_at = models.DateTimeField(null=True, blank=True)

class EmailTemplate(models.Model):
    key = models.CharField(max_length=100, unique=True)
    subject = models.CharField(max_length=255)
    body = models.TextField()

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

