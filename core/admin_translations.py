"""TranslationAdminMixin: a ModelAdmin for a core.content_languages
TranslatableModel gets one collapsible "In <language>" fieldset per extra
language of the object, editing its `translations`. The normal fields stay
the main language. Put it first in the bases:
`class PathwayAdmin(TranslationAdminMixin, admin.ModelAdmin)`."""

from django import forms
from django.db import models
from django.utils.translation import gettext as _

from .content_languages import language_name, save_translation_fields, translation_field_name


class TranslationAdminMixin:
    def _translation_languages(self, obj):
        return (obj if obj is not None else self.model()).content_languages()[1:]

    def _translation_fields(self, obj):
        model_fields = {f.name: f for f in self.model._meta.fields}
        fields = {}
        for language in self._translation_languages(obj):
            for name in self.model.TRANSLATABLE_FIELDS:
                model_field = model_fields[name]
                widget = (forms.Textarea(attrs={"rows": 3, "cols": 80}) if isinstance(model_field, models.TextField)
                          else forms.TextInput(attrs={"size": 80}))
                fields[translation_field_name(language, name)] = forms.CharField(
                    required=False, widget=widget, max_length=getattr(model_field, "max_length", None),
                    label=f"{str(model_field.verbose_name).capitalize()} ({language_name(language)})",
                )
        return fields

    def get_form(self, request, obj=None, change=False, **kwargs):
        extra = self._translation_fields(obj)
        base = kwargs.get("form", self.form)

        def __init__(form, *args, **init_kwargs):
            base.__init__(form, *args, **init_kwargs)
            for field_name in extra:
                _prefix, language, field = field_name.split("__")
                form.initial.setdefault(field_name, form.instance.translation_for(language, field))

        kwargs["form"] = type(base.__name__, (base,), {**extra, "__init__": __init__})
        return super().get_form(request, obj, change, **kwargs)

    def get_fieldsets(self, request, obj=None):
        names = set(self._translation_fields(obj))
        fieldsets = [
            (title, {**options, "fields": [f for f in options["fields"] if f not in names]})
            for title, options in super().get_fieldsets(request, obj)
        ]
        for language in self._translation_languages(obj):
            fieldsets.append((
                _("In %(language)s") % {"language": language_name(language)},
                {"classes": ["collapse"],
                 "fields": [translation_field_name(language, f) for f in self.model.TRANSLATABLE_FIELDS]},
            ))
        return fieldsets

    def save_model(self, request, obj, form, change):
        save_translation_fields(form, obj)
        super().save_model(request, obj, form, change)
