"""`{% site_version as version %}`: the running version, and
`{% site_checkout as checkout %}`: in development, the branch and commit
(core.version)."""

from django import template

from core.version import checkout, version

register = template.Library()


@register.simple_tag
def site_version():
    return version()


@register.simple_tag
def site_checkout():
    return checkout()
