from django import template
from django.conf import settings
from django.utils.translation import get_language

register = template.Library()

# The help centre's folder per site language; English is at its root.
_LANGUAGE_FOLDERS = {"nl": "nl/", "fr": "fr/"}


@register.simple_tag
def help_url(page):
    """A help-centre page (`volunteering/start-a-new-dojo`, as under
    docs/source/) in the page's language: {% help_url "faq" %}."""
    folder = _LANGUAGE_FOLDERS.get((get_language() or "")[:2], "")
    return f"{settings.HELP_CENTRE_URL.rstrip('/')}/{folder}{page}.html"
