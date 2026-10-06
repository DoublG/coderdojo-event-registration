import re

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


HEADING = re.compile(r"<(/?)h([1-6])\b")


def _fit_headings(html, start):
    """Fit the text's headings under the page's own: its highest heading becomes
    <h`start`> and the others follow without gaps, whatever levels the author
    typed (a lone `###` is the first heading under the page's, not three levels
    down). Screen-reader users navigate by heading level (WCAG 1.3.1)."""
    levels = sorted({int(level) for level in re.findall(r"<h([1-6])\b", html)})
    to = {level: min(start + i, 6) for i, level in enumerate(levels)}
    return HEADING.sub(lambda m: f"<{m.group(1)}h{to[int(m.group(2))]}", html)


@register.filter(name="markdownify")
def markdownify(text, start=2):
    """Render staff-authored Markdown (dojo and session descriptions etc.) to
    HTML with only basic formatting. The source text is HTML-escaped before it
    reaches the Markdown parser, so any HTML a mentor types shows as text, and
    the result is cleaned against ALLOWED_TAGS. Headings start at <h`start`>:
    <h2> by default (the page's own title is its <h1>), `|markdownify:3` for a
    text under one of the page's <h2>s."""
    if not text:
        return ""
    html = _fit_headings(md.markdown(escape(text), extensions=["nl2br"]), int(start))
    clean = nh3.clean(
        html,
        tags=ALLOWED_TAGS,
        attributes=ALLOWED_ATTRIBUTES,
        url_schemes=ALLOWED_URL_SCHEMES,
        link_rel="nofollow noopener noreferrer",
    )
    return mark_safe(clean)  # noqa: S308 (escaped, then cleaned against the allowlist above)
