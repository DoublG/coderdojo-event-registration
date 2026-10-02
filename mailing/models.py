from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from .categories import MailCategory


class EmailTemplate(models.Model):
    """Subject and plain-text body in Django template syntax, one row per
    key and language. Rendered by mailing.rendering.render(), which falls
    back to MAILING_FALLBACK_LANGUAGE when a language is missing."""

    key = models.CharField(max_length=100)
    language = models.CharField(max_length=10, choices=settings.LANGUAGES)
    category = models.CharField(max_length=20, choices=MailCategory.choices)
    description = models.CharField(max_length=255, blank=True, help_text="When it's sent and which variables it uses.")
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
        PENDING = "pending", _("Pending")
        SENDING = "sending", _("Sending")
        SENT = "sent", _("Sent")
        FAILED = "failed", _("Failed")
        BOUNCED = "bounced", _("Bounced")
        SUPPRESSED = "suppressed", _("Not sent (no consent, no address or blocked)")

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
    campaign = models.ForeignKey("campaigns.Campaign", null=True, blank=True, on_delete=models.SET_NULL)
    # The dojo a `dojo_news` mail is from: a family that muted it doesn't get
    # it (checked again right before sending), and its unsubscribe link
    # offers "not from this dojo" (DATA_MODEL.md §25).
    dojo = models.ForeignKey("dojos.Dojo", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    # Replies go here instead of the organisation: a dojo mailing's dojo address.
    reply_to = models.EmailField(blank=True)

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
        default=False,
        help_text="A campaign test sent to its author: preferences don't apply (blocks still do).",
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
        return super().get_queryset().select_related("user", "dojo")


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
        (SIGNUP, _("Sign-up form")),
        (PREFERENCES, _("Mail preferences page")),
        (UNSUBSCRIBE_LINK, _("Unsubscribe link")),
        (ADMIN, _("Admin")),
        (BOUNCE, _("Bounce or complaint")),
    ]

    user = models.ForeignKey("accounts.User", on_delete=models.CASCADE, related_name="consent_events")
    category = models.CharField(max_length=20, choices=MailCategory.choices)
    # Set when the change is about one dojo's mail only (DojoMailMute).
    dojo = models.ForeignKey("dojos.Dojo", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    subscribed = models.BooleanField()
    source = models.CharField(max_length=20, choices=SOURCE_CHOICES)
    wording_version = models.CharField(max_length=20, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = ConsentEventManager()

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        where = f" from {self.dojo}" if self.dojo_id else ""
        return f"{self.user}: {self.category}{where} {'on' if self.subscribed else 'off'} ({self.source})"


class DojoMailMuteManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().select_related("user", "dojo")


class DojoMailMute(models.Model):
    """An account doesn't want `dojo_news` mail from this one dojo (its own
    mailings and the automated "new sessions" mail), while still getting
    other dojos' (DATA_MODEL.md §25). Changed only through
    mailing.preferences.set_dojo_mute, which also logs a ConsentEvent."""

    user = models.ForeignKey("accounts.User", on_delete=models.CASCADE, related_name="dojo_mail_mutes")
    dojo = models.ForeignKey("dojos.Dojo", on_delete=models.CASCADE, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    objects = DojoMailMuteManager()

    class Meta:
        constraints = [models.UniqueConstraint(fields=["user", "dojo"], name="unique_dojo_mail_mute")]

    def __str__(self):
        return f"{self.user}: muted {self.dojo}"


class EmailSuppression(models.Model):
    """An address nothing is sent to any more, whatever the preferences:
    a hard bounce, a spam complaint, or blocked by hand."""

    HARD_BOUNCE = "hard_bounce"
    SOFT_BOUNCES = "soft_bounces"
    COMPLAINT = "complaint"
    MANUAL = "manual"
    REASON_CHOICES = [
        (HARD_BOUNCE, _("Hard bounce")),
        (SOFT_BOUNCES, _("Repeated soft bounces")),
        (COMPLAINT, _("Spam complaint")),
        (MANUAL, _("Blocked by hand")),
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
    KIND_CHOICES = [
        (HARD, _("Hard bounce (5.x.x)")),
        (SOFT, _("Soft bounce (4.x.x)")),
        (COMPLAINT, _("Spam complaint")),
    ]

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
