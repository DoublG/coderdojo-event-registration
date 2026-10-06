"""Template helpers for texts a dojo writes in its own languages
(core.content_languages): {{ dojo|localized:"description" }}, the
{% only_in text %} note when that text isn't in the page's language,
{{ text|in_lang }} to mark such a text's own language (WCAG 3.1.2), and
{{ dojo.languages|language_names }}."""

from django import template
from django.utils.html import format_html
from django.utils.translation import get_language
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
    # The note is in the page's language, even inside a text marked with its own.
    return format_html(
        '<span class="cd-badge cd-badge--outline caption content-lang-note" lang="{}">{}</span>',
        get_language(),
        _("Only in %(language)s") % {"language": text.language_name},
    )


@register.filter
def in_lang(text):
    """A text shown in another language than the page's (the dojo's main
    language, because there's no version in the page's) wrapped in
    <span lang="..">, so a screen reader reads it in that language. Any other
    text comes back as it is. Only for text in the page, never in an attribute
    or a <title>."""
    if not getattr(text, "is_fallback", False):
        return text
    return format_html('<span lang="{}">{}</span>', text.language, text)


@register.filter
def language_names(codes):
    return ", ".join(language_name(code) for code in codes or [])
