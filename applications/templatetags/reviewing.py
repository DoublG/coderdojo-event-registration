"""Counts for the organisation sidebar's Volunteers links (DATA_MODEL.md §21),
shown to reviewers only (core/_manage_base.html)."""

from django import template

from accounts.models import User
from applications.models import Application

register = template.Library()


@register.simple_tag
def checks_awaiting_review_count():
    """Uploaded background-check documents nobody has decided on yet."""
    return User.objects.filter(background_check_status=User.CHECK_SUBMITTED).count()


@register.simple_tag
def applications_pending_count():
    return Application.objects.filter(status=Application.PENDING).count()
