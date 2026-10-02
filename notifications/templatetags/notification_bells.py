"""The organisation dashboard's notification bell (a dojo's is in its admin
base template), kept with the notifications it shows."""

from django import template

register = template.Library()


@register.inclusion_tag("dojos/partials/_notification_bell.html", takes_context=True)
def organisation_bell(context):
    """The organisation dashboard's notification bell (DATA_MODEL.md §23)."""
    from ..consumers import organisation_notification_context

    return {**organisation_notification_context(context["request"].user), "csrf_token": context.get("csrf_token")}
