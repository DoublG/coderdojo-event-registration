"""`{% site_version as version %}`: the running version (core.version)."""

from django import template

from core.version import version

register = template.Library()


@register.simple_tag
def site_version():
    return version()
