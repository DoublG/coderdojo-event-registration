"""Rendering EmailTemplate rows: pick the recipient's language, fill in the
variables. Plain text, so no HTML autoescaping."""

from django.conf import settings
from django.template import Context, Template
from django.utils import translation

from .models import EmailTemplate

FALLBACK_LANGUAGE = "en-us"


class TemplateMissing(Exception):
    pass


def get_template(key, language):
    """The template in `language`, else in the fallback language."""
    fallback = getattr(settings, "MAILING_FALLBACK_LANGUAGE", FALLBACK_LANGUAGE)
    templates = {t.language: t for t in EmailTemplate.objects.filter(key=key, language__in=[language, fallback])}
    template = templates.get(language) or templates.get(fallback)
    if template is None:
        raise TemplateMissing(f"No email template “{key}” in {language} or {fallback}.")
    return template


def render(key, language, context):
    """(subject, body) for template `key` in `language` with `context`."""
    template = get_template(key, language)
    ctx = Context(context, autoescape=False)
    # The active language decides how |date prints day and month names.
    with translation.override(template.language):
        subject = Template(template.subject).render(ctx)
        body = Template(template.body).render(ctx)
    return " ".join(subject.split()), body.strip() + "\n"
