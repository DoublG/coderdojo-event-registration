"""Mail templates: every template with its languages and what uses it, editing
one language with a preview on example data, new campaign templates, and
deleting a language or a campaign template (never one the site sends itself)."""

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import redirect, render
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from accounts.organisation import Area, require_area

from .. import template_users
from ..forms import NewTemplateForm, TemplateVersionForm
from ..models import EmailTemplate
from ..rendering import FALLBACK_LANGUAGE
from ..rendering import render as render_template
from ..seed_templates import GENERIC_SAMPLE_CONTEXT, SAMPLE_CONTEXT, SYSTEM_TEMPLATE_KEYS

# --- mail templates -------------------------------------------------------------------


def _sample_context(key):
    return {**GENERIC_SAMPLE_CONTEXT, **SAMPLE_CONTEXT.get(key, {})}


@login_required
def template_list(request):
    require_area(request, Area.COMMUNICATION)
    languages = dict(settings.LANGUAGES)
    rows = {}
    for template in EmailTemplate.objects.order_by("key", "language"):
        row = rows.setdefault(
            template.key,
            {
                "key": template.key,
                "category": template.get_category_display(),
                "description": template.description,
                "languages": [],
            },
        )
        row["languages"].append(languages.get(template.language, template.language))
    used_by = template_users.names_by_key()
    for key, row in rows.items():
        row["system"] = key in SYSTEM_TEMPLATE_KEYS
        row["campaigns"] = used_by.get(key, [])
    return render(request, "mailing/manage/template_list.html", {"rows": rows.values(), "active": "templates"})


@login_required
def template_create(request):
    require_area(request, Area.COMMUNICATION)
    form = NewTemplateForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        EmailTemplate.objects.create(
            key=form.cleaned_data["key"],
            language=FALLBACK_LANGUAGE,
            category=form.cleaned_data["category"],
            description=form.cleaned_data["description"],
            subject="{{ recipient_name }}, ...",
            body="Hi {{ recipient_name }},\n\n...\n\nThe CoderDojo Belgium team\n\n--\n"
            "You get this mail because of your mail preferences. Unsubscribe: {{ unsubscribe_url }}",
        )
        messages.success(
            request,
            _(
                "Template created. Write the English version first: it's used for every language that has no version of its own."
            ),
        )
        return redirect("manage_template_edit", key=form.cleaned_data["key"], language=FALLBACK_LANGUAGE)
    return render(request, "mailing/manage/template_new.html", {"form": form, "active": "templates"})


@login_required
def template_edit(request, key, language):
    require_area(request, Area.COMMUNICATION)
    languages = dict(settings.LANGUAGES)
    if language not in languages:
        raise Http404
    versions = {t.language: t for t in EmailTemplate.objects.filter(key=key)}
    if not versions:
        raise Http404
    english = versions.get(FALLBACK_LANGUAGE) or next(iter(versions.values()))
    template = versions.get(language) or EmailTemplate(
        key=key,
        language=language,
        category=english.category,
        description=english.description,
        subject=english.subject,
        body=english.body,
    )
    sample = _sample_context(key)
    form = TemplateVersionForm(request.POST or None, instance=template, sample_context=sample)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, _("%(language)s version saved.") % {"language": languages[language]})
        return redirect("manage_template_edit", key=key, language=language)
    preview = None
    if template.pk and not form.errors:
        preview = render_template(key, language, sample)
    return render(
        request,
        "mailing/manage/template_edit.html",
        {
            "form": form,
            "key": key,
            "language": language,
            "language_name": languages[language],
            "tabs": [(code, name, code in versions) for code, name in settings.LANGUAGES],
            "is_new_version": template.pk is None,
            "preview": preview,
            "category": english.get_category_display(),
            "system": key in SYSTEM_TEMPLATE_KEYS,
            "fallback": FALLBACK_LANGUAGE,
            "sample_names": sorted(sample),
            "active": "templates",
        },
    )


@login_required
@require_POST
def template_delete(request, key, language=None):
    """Delete one language version, or (language empty) a whole campaign
    template. The site's own templates, and the English fallback of any
    template, stay; so does a template a draft campaign still uses."""
    require_area(request, Area.COMMUNICATION)
    versions = EmailTemplate.objects.filter(key=key)
    if not versions.exists():
        raise Http404
    if language:
        if language == FALLBACK_LANGUAGE:
            messages.error(request, _("The English version is the fallback for every language: it can't be deleted."))
        else:
            versions.filter(language=language).delete()
            messages.success(request, _("That language version is deleted; English is used instead."))
        return redirect("manage_template_edit", key=key, language=FALLBACK_LANGUAGE)
    if key in SYSTEM_TEMPLATE_KEYS:
        messages.error(request, _("The site sends this template itself: it can be edited, not deleted."))
    elif template_users.still_needed(key):
        messages.error(request, _("A campaign that hasn't gone out yet uses this template."))
    else:
        versions.delete()
        messages.success(request, _("Template “%(key)s” deleted.") % {"key": key})
        return redirect("manage_template_list")
    return redirect("manage_template_edit", key=key, language=FALLBACK_LANGUAGE)
