from django.conf import settings
from django.db import models


class NotificationManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().select_related("recipient")


class Notification(models.Model):
    recipient = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications")
    dojo = models.ForeignKey(
        "dojos.Dojo", on_delete=models.CASCADE, null=True, blank=True, related_name="notifications",
        help_text="The dojo this notification concerns, if any — lets a multi-dojo owner's admin "
                  "panel (dojos.views._notification_context) show only the dojo currently being "
                  "managed. Read state stays per-recipient regardless (see `read` below): a "
                  "dojo-level event that concerns more than one person fans out to one row per "
                  "recipient, sharing the same dojo/text/url but each with its own independent read "
                  "flag — see notifications.services.notify.",
    )
    text = models.CharField(max_length=300)
    url = models.CharField(max_length=300, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    read = models.BooleanField(default=False)

    objects = NotificationManager()

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.recipient}: {self.text}"
