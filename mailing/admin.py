from django.contrib import admin
from django.utils.html import format_html_join

from .models import (
    BounceRecord,
    ConsentEvent,
    DojoMailMute,
    EmailMessage,
    EmailSuppression,
    EmailTemplate,
    MailPreference,
)
from .rendering import render
from .seed_templates import SAMPLE_CONTEXT


@admin.register(EmailTemplate)
class EmailTemplateAdmin(admin.ModelAdmin):
    list_display = ["key", "language", "category", "subject"]
    list_filter = ["category", "language"]
    search_fields = ["key", "subject", "body"]
    readonly_fields = ["preview"]

    @admin.display(description="Preview with example data")
    def preview(self, obj):
        if obj.pk is None or obj.key not in SAMPLE_CONTEXT:
            return "—"
        subject, body = render(obj.key, obj.language, SAMPLE_CONTEXT[obj.key])
        return format_html_join("", "<pre style='white-space: pre-wrap'>{}</pre>", [(f"{subject}\n\n{body}",)])


@admin.register(EmailMessage)
class EmailMessageAdmin(admin.ModelAdmin):
    """The mail queue and its history. Rows are created by
    mailing.services.send() and changed by the Celery tasks; edit one here
    only to fix something by hand (e.g. put a stuck row back to pending)."""

    list_display = ["recipient", "category", "subject", "status", "attempts", "created_at", "sent_at"]
    list_filter = ["status", "category", "campaign"]
    search_fields = ["recipient", "subject", "message_id"]
    date_hierarchy = "created_at"


@admin.register(MailPreference)
class MailPreferenceAdmin(admin.ModelAdmin):
    """Preferences change through the account's own Mail preferences page or
    an unsubscribe link, which also log a ConsentEvent. An edit here does
    NOT log one: only for fixing something by hand (and note why)."""

    list_display = ["user", "category", "subscribed", "changed_at"]
    list_filter = ["category", "subscribed"]
    search_fields = ["user__email", "user__username"]


@admin.register(ConsentEvent)
class ConsentEventAdmin(admin.ModelAdmin):
    """The consent log, append-only in normal use (mailing.preferences).
    Editable here only for emergencies, e.g. erasing a person's data."""

    list_display = ["created_at", "user", "category", "dojo", "subscribed", "source", "wording_version"]
    list_filter = ["category", "source", "subscribed"]
    search_fields = ["user__email", "user__username"]


@admin.register(DojoMailMute)
class DojoMailMuteAdmin(admin.ModelAdmin):
    """Dojos an account muted (DATA_MODEL.md §25). They change through Mail
    preferences or a dojo mail's unsubscribe link, which also log a
    ConsentEvent. An edit here does NOT log one: only for fixing something
    by hand (and note why)."""

    list_display = ["user", "dojo", "created_at"]
    list_filter = ["dojo"]
    search_fields = ["user__email", "user__username", "dojo__name"]


@admin.register(BounceRecord)
class BounceRecordAdmin(admin.ModelAdmin):
    """What came back from the bounce mailbox (append-only in normal use)."""

    list_display = ["created_at", "email", "kind", "status_code", "diagnostic"]
    list_filter = ["kind"]
    search_fields = ["email", "diagnostic"]


@admin.register(EmailSuppression)
class EmailSuppressionAdmin(admin.ModelAdmin):
    list_display = ["email", "reason", "note", "created_at"]
    list_filter = ["reason"]
    search_fields = ["email"]
