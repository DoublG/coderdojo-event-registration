"""Texts a dojo writes itself, in the languages it supports (DATA_MODEL.md §19).

A dojo picks its languages (`Dojo.languages`, in order; the first is its
main language). Those are the languages its sessions are given in and the
languages it writes its texts in. A translatable model keeps its main-
language text in the normal columns and the other languages in
`translations` ({"fr-be": {"description": "..."}}), and says which fields
are translatable (TRANSLATABLE_FIELDS) and whose languages apply
(`content_languages()`).

`localized(obj, field)` gives the text in the page's language when the dojo
wrote one, else the main-language text, flagged `is_fallback` so the page
can say "only in Nederlands". Templates use the `localized` filter and the
`only_in` tag from core.templatetags.content_i18n.
"""

from django.conf import settings
from django.db import models
from django.utils import translation

LANGUAGE_CODES = [code for code, _name in settings.LANGUAGES]


def language_name(code):
    return dict(settings.LANGUAGES).get(code, code)


def normalize(code):
    """A LANGUAGES code for `code` ("nl", "nl-BE", "nl_be" → "nl-be"), or None."""
    if not code:
        return None
    code = code.lower().replace("_", "-")
    if code in LANGUAGE_CODES:
        return code
    return next((c for c in LANGUAGE_CODES if c.split("-")[0] == code.split("-")[0]), None)


def clean_languages(codes):
    """Known codes only, in order, without repeats."""
    seen = []
    for code in codes or []:
        code = normalize(code)
        if code and code not in seen:
            seen.append(code)
    return seen


class LocalizedText(str):
    """A string that remembers which language it's in, and whether that's a
    fallback (the visitor's language wasn't available)."""

    def __new__(cls, text, language, is_fallback):
        obj = super().__new__(cls, text)
        obj.language = language
        obj.is_fallback = is_fallback
        return obj

    @property
    def language_name(self):
        return language_name(self.language)


class TranslatableModel(models.Model):
    TRANSLATABLE_FIELDS = ()

    translations = models.JSONField(
        default=dict, blank=True,
        help_text='The texts in the dojo\'s other languages: {"fr-be": {"field": "text"}}. The normal fields '
                  "hold the main language. Edited on the dojo's dashboard pages.",
    )

    class Meta:
        abstract = True

    def content_languages(self):
        raise NotImplementedError

    def main_language(self):
        languages = self.content_languages()
        return languages[0] if languages else LANGUAGE_CODES[0]

    def translation_for(self, language, field):
        return ((self.translations or {}).get(language) or {}).get(field, "")

    def set_translation(self, language, field, text):
        translations = dict(self.translations or {})
        texts = dict(translations.get(language) or {})
        if text:
            texts[field] = text
        else:
            texts.pop(field, None)
        if texts:
            translations[language] = texts
        else:
            translations.pop(language, None)
        self.translations = translations

    def localized(self, field, language=None):
        assert field in self.TRANSLATABLE_FIELDS, field
        base = getattr(self, field) or ""
        main = self.main_language()
        wanted = normalize(language or translation.get_language()) or main
        if wanted == main:
            return LocalizedText(base, main, False)
        text = self.translation_for(wanted, field) if wanted in self.content_languages() else ""
        if text:
            return LocalizedText(text, wanted, False)
        # Only a fallback worth mentioning when there's something to show.
        return LocalizedText(base, main, bool(base))


def localized(obj, field, language=None):
    return obj.localized(field, language)


def translation_field_name(language, field):
    return f"tr__{language}__{field}"


def add_translation_fields(form, instance, make_field):
    """Add one form field per (other language, translatable field) of
    `instance` to `form`, initialised from its translations; returns the
    groups for the template: [(language, language_name, [field names])].
    `make_field(field)` builds an empty form field like the main one."""
    groups = []
    for language in instance.content_languages()[1:]:
        names = []
        for field in instance.TRANSLATABLE_FIELDS:
            name = translation_field_name(language, field)
            form.fields[name] = make_field(field)
            form.initial[name] = instance.translation_for(language, field)
            names.append(name)
        groups.append((language, language_name(language), names))
    return groups


def save_translation_fields(form, instance):
    for language in instance.content_languages()[1:]:
        for field in instance.TRANSLATABLE_FIELDS:
            name = translation_field_name(language, field)
            if name in form.cleaned_data:
                instance.set_translation(language, field, (form.cleaned_data[name] or "").strip())


def optional_copy(form_field, label):
    """An optional text field that looks like `form_field` (same widget,
    without its example placeholder), for one translation of it."""
    import copy

    from django import forms

    widget = copy.deepcopy(form_field.widget)
    widget.attrs.pop("placeholder", None)
    return forms.CharField(required=False, label=label, widget=widget, max_length=getattr(form_field, "max_length", None))


def bound_translation_groups(form, groups):
    """add_translation_fields' groups with bound fields, for templates:
    [{"code", "name", "fields": [BoundField, ...]}]."""
    return [{"code": code, "name": name, "fields": [form[n] for n in names]} for code, name, names in groups]
