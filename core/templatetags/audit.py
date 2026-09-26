from django import template

from core.audit import log_access

register = template.Library()


@register.simple_tag
def audit_view(obj):
    """`{% audit_view ninja %}`: records in the audit log that this page
    showed `obj`'s special-category data (core.audit.log_access). A tag with
    a side effect on purpose: placed inside the block that prints the data,
    it records exactly what was shown, whichever view rendered it (the
    attendance list is rendered by several, whole or one row at a time)."""
    log_access(obj)
    return ""
