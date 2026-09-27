from django import template

from core.jsi18n import catalog_url

register = template.Library()


@register.simple_tag
def javascript_catalog_url():
    """The JavaScript catalog for the page's language, at its cacheable
    versioned URL (core.jsi18n)."""
    return catalog_url()
