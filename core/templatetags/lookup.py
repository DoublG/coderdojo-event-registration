from django import template

register = template.Library()


@register.filter
def get_item(mapping, key):
    """`mapping|get_item:key`: a dict lookup by a variable key (the template
    language can only do fixed keys), None when absent."""
    return mapping.get(key) if hasattr(mapping, "get") else None
