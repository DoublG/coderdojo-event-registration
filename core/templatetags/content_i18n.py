"""Template helpers for texts a dojo writes in its own languages
(core.content_languages): {{ dojo|localized:"description" }}, the
{% only_in text %} note when that text isn't in the page's language, and
{{ dojo.languages|language_names }}."""

from django import template
from django.utils.html import format_html
from django.utils.translation import gettext as _

from core.content_languages import language_name

register = template.Library()


@register.filter
def localized(obj, field):
    return obj.localized(field) if obj is not None else ""


@register.simple_tag
def only_in(text):
    """A small "Only in Nederlands" label after a text shown in the dojo's
    main language because it has no version in the page's language."""
    if not getattr(text, "is_fallback", False):
        return ""
    return format_html(
        '<span class="cd-badge cd-badge--outline caption content-lang-note" lang="{}">{}</span>',
        text.language, _("Only in %(language)s") % {"language": text.language_name},
    )


@register.filter
def language_names(codes):
    return ", ".join(language_name(code) for code in codes or [])
