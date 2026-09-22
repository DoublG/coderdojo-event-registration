import markdown as md
from django import template
from django.utils.html import escape
from django.utils.safestring import mark_safe

register = template.Library()


@register.filter(name="markdownify")
def markdownify(text):
    """Render staff-authored Markdown (session/dojo descriptions etc.) to
    HTML. The source text is HTML-escaped before it reaches the Markdown
    parser, so any literal '<' or '>' a mentor types is inert rather than
    passed through as raw HTML — Markdown syntax itself doesn't need angle
    brackets, so this doesn't affect **bold**, [links](url) or lists."""
    if not text:
        return ""
    html = md.markdown(escape(text), extensions=["fenced_code", "nl2br"])
    return mark_safe(html)
