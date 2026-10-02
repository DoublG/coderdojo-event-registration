from django import template

from accounts.manage_nav import request_manage_contexts

register = template.Library()


@register.inclusion_tag("core/partials/_manage_switcher.html", takes_context=True)
def manage_switcher(context, dojo=None, role_label=""):
    """The top of the management sidebar (core/_manage_shell.html): the
    context being managed (the organisation, or `dojo`) and, when the
    account can manage more than one, a menu to switch (accounts.manage_nav).
    A dojo in the menu opens on the same page as now when that's Settings,
    else on its dashboard."""
    return {
        "contexts": request_manage_contexts(context["request"]),
        "dojo": dojo,
        "role_label": role_label,
        "active": context.get("active"),
    }


@register.simple_tag(takes_context=True)
def manage_contexts(context):
    """accounts.manage_nav's contexts for the request's account, e.g. for the
    Organisation sidebar's links to organisation events."""
    return request_manage_contexts(context["request"])
