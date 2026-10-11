from django.contrib import admin

from .models import Report


@admin.register(Report)
class ReportAdmin(admin.ModelAdmin):
    """Saved reports; day to day they're made on the organisation dashboard
    (/manage/reports/). Editing `config` here bypasses the conversion to
    language-independent references (reports.config): keep its col:/val:
    references intact."""

    list_display = ("name", "dataset", "updated_at", "updated_by")
    list_filter = ("dataset",)
    search_fields = ("name", "description")
    readonly_fields = ("created_at", "updated_at")
