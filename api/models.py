from django.conf import settings
from django.db import models
from oauth2_provider.settings import oauth2_settings


class DojoApiClient(models.Model):
    """An app or website that works for one dojo through the API
    (DATA_MODEL.md §13), made by the dojo's champion. It logs in with the
    OAuth 2.0 client credentials of its `application` (django-oauth-toolkit;
    the secret is stored hashed) and may only use its `scopes`. It acts as
    its own technical `account` (account_type "service"): that's who marked
    what, in the data and in the audit log. Deleting it (api.services)
    removes this row, the application and its tokens, and switches the
    account off, which stays for the history."""

    READ = "attendance:read"
    WRITE = "attendance:write"
    SCOPE_CHOICES = [(READ, "See the sessions and who has a place"), (WRITE, "Mark who came")]

    dojo = models.ForeignKey("dojos.Dojo", on_delete=models.CASCADE, related_name="api_clients")
    name = models.CharField(max_length=100, help_text='What the dojo calls it, e.g. "Scan app at the door".')
    scopes = models.JSONField(default=list, help_text="What it may do: attendance:read, attendance:write.")
    application = models.OneToOneField(
        oauth2_settings.APPLICATION_MODEL,
        on_delete=models.CASCADE,
        related_name="dojo_client",
        help_text="Its OAuth 2.0 client (ID and hashed secret).",
    )
    account = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="api_client",
        limit_choices_to={"account_type": "service"},
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.name
