from django.conf import settings
from django.db import models


class ErasureRecord(models.Model):
    """One erased person (an account or a child), DATA_MODEL.md §16 phase 5:
    which row, when, why and at whose request, never who they were. After a
    backup is restored, `manage.py privacy_replay_erasures` erases them again
    from these rows."""

    # The account holder deleted their own account; REQUEST is the
    # organisation acting on a request by mail or post.
    SELF = "self"
    REQUEST = "request"
    RETENTION = "retention"
    REASON_CHOICES = [
        (SELF, "By the account holder"),
        (REQUEST, "On request, by the organisation"),
        (RETENTION, "Retention: two years without logging in"),
    ]

    # "accounts.User" or "accounts.Ninja".
    model = models.CharField(max_length=100)
    object_id = models.PositiveBigIntegerField()
    # Cleaned instead of erased: a champion's or mentor's visible name and,
    # when shown, their team-page profile were kept.
    keep_visible = models.BooleanField(default=False)
    reason = models.CharField(max_length=20, choices=REASON_CHOICES)
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        help_text="The organisation admin who asked for it; empty for the retention job.",
    )
    erased_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=["model", "object_id"])]

    def __str__(self):
        return f"{self.model} #{self.object_id} ({self.reason}, {self.erased_at:%Y-%m-%d})"


class RetentionNotice(models.Model):
    """That an account was told it will be deleted for not logging in
    (DATA_MODEL.md §16 phase 4, `privacy.retention`): one per reminder,
    per period of inactivity (`inactive_since`, the last login it was
    about). `days_before` 0 is no mail but the notice that the date passed
    while the account is still the champion of an active dojo."""

    account = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="retention_notices")
    inactive_since = models.DateTimeField()
    days_before = models.PositiveSmallIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["account", "inactive_since", "days_before"], name="unique_retention_notice"
            )
        ]

    def __str__(self):
        return f"#{self.account_id}: {self.days_before} days before ({self.created_at:%Y-%m-%d})"
