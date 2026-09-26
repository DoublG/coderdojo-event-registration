from django.contrib import admin

from .models import ErasureRecord, RetentionNotice


@admin.register(ErasureRecord)
class ErasureRecordAdmin(admin.ModelAdmin):
    """The log of erasures (privacy.erasure): what `privacy_replay_erasures`
    erases again after a backup is restored. Editing or deleting a row here
    changes what a replay does, and erases nothing by itself."""

    list_display = ["model", "object_id", "reason", "keep_visible", "erased_at"]
    list_filter = ["model", "reason", "keep_visible"]
    search_fields = ["object_id"]


@admin.register(RetentionNotice)
class RetentionNoticeAdmin(admin.ModelAdmin):
    """The retention job's reminders (privacy.retention). Deleting one makes
    the job send that reminder again, and a deleted first reminder moves the
    date to a month after the next one; adding one bypasses the mail."""

    list_display = ["account", "days_before", "inactive_since", "created_at"]
    list_filter = ["days_before"]
    raw_id_fields = ["account"]
    search_fields = ["account__username", "account__email"]
