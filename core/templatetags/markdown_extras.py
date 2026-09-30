import markdown as md
import nh3
from django import template
from django.utils.html import escape
from django.utils.safestring import mark_safe

register = template.Library()

# What a team's Markdown may become: headings, paragraphs, bold, italic, lists and
# links, the basic formatting the fields' help texts promise. Anything else
# Markdown makes (images, code, quotes, rules) is dropped, keeping its text.
ALLOWED_TAGS = {"p", "br", "h2", "h3", "h4", "h5", "h6", "strong", "em", "ul", "ol", "li", "a"}
ALLOWED_ATTRIBUTES = {"a": {"href", "title"}}
# Never javascript: or data: links; relative links to our own pages stay allowed.
ALLOWED_URL_SCHEMES = {"http", "https", "mailto"}


@register.filter(name="markdownify")
def markdownify(text):
    """Render staff-authored Markdown (dojo and session descriptions etc.) to
    HTML with only basic formatting. The source text is HTML-escaped before it
    reaches the Markdown parser, so any HTML a mentor types shows as text, and
    the result is cleaned against ALLOWED_TAGS. Headings start at <h2> (`#` is
    an h2), since the page's own title is its <h1>."""
    if not text:
        return ""
    html = md.markdown(
        escape(text),
        extensions=["nl2br", "toc"],
        extension_configs={"toc": {"baselevel": 2}},
    )
    clean = nh3.clean(
        html,
        tags=ALLOWED_TAGS,
        attributes=ALLOWED_ATTRIBUTES,
        url_schemes=ALLOWED_URL_SCHEMES,
        link_rel="nofollow noopener noreferrer",
    )
    return mark_safe(clean)  # noqa: S308 (escaped, then cleaned against the allowlist above)
