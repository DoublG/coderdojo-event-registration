"""How the site's forms render (settings.FORM_RENDERER).

Django renders every field through one template, core/forms/field.html (a
`cd-form__field`: label with the required mark, the widget, help text, then
errors), and a whole form through core/forms/form.html. A template shows a
field with `{{ form.name.as_field_group }}` (keeping its own rows around it)
or a whole plain form with `{{ form }}`. Labels and help texts belong on the
Form, not in the template.

SiteBoundField gives each widget the site's input class by its type, so a
Form doesn't have to set `attrs={"class": ...}`; a class a widget sets itself
still wins. The Django admin renders with the same renderer but keeps its
own field layout; the classes it gets there do nothing (no bundle.css).
"""

from typing import NamedTuple

from django import forms
from django.forms.renderers import TemplatesSetting
from django.forms.widgets import Input
from django.http import QueryDict

INPUT_CLASS = "cd-form__input body"
SELECT_CLASS = "cd-form__select body"
TEXTAREA_CLASS = "cd-form__textarea body"

# Laid out by field.html itself (checkbox rows, option lists), never boxed.
UNSTYLED_WIDGETS = (
    forms.CheckboxInput,
    forms.RadioSelect,
    forms.CheckboxSelectMultiple,
    forms.HiddenInput,
    forms.MultipleHiddenInput,
)


def widget_class(widget):
    """The site's CSS class for `widget`, or None."""
    if isinstance(widget, UNSTYLED_WIDGETS):
        return None
    if isinstance(widget, forms.Select):
        return SELECT_CLASS
    if isinstance(widget, forms.Textarea):
        return TEXTAREA_CLASS
    if isinstance(widget, Input):
        return INPUT_CLASS
    return None


class SiteBoundField(forms.BoundField):
    def build_widget_attrs(self, attrs, widget=None):
        attrs = super().build_widget_attrs(attrs, widget)
        widget = widget or self.field.widget
        if "class" not in attrs and "class" not in widget.attrs and (css := widget_class(widget)):
            attrs["class"] = css
        return attrs


class SiteFormRenderer(TemplatesSetting):
    """TemplatesSetting, so the project's templates can override Django's
    widget templates too (core/templates/django/forms/widgets/)."""

    form_template_name = "core/forms/form.html"
    field_template_name = "core/forms/field.html"
    bound_field_class = SiteBoundField


class ActiveFilter(NamedTuple):
    label: str
    value: str
    remove_url: str


class SearchFiltersMixin:
    """A GET search form whose applied filters show as chips above the
    results (core/partials/_active_filters.html), each with a link that
    drops only that filter. `filter_fields` are the fields shown as chips,
    in order; `filter_also_removes` names other query keys a field's link
    drops too. An invalid form applies no filter, so it shows none."""

    filter_fields = ()
    filter_also_removes = {}

    def active_filters(self, path):
        if not self.is_valid():
            return []
        filters = []
        for name in self.filter_fields:
            raw = str(self.data.get(name, "")).strip()
            if raw:
                keys = (name, *self.filter_also_removes.get(name, ()))
                filters.append(
                    ActiveFilter(self.fields[name].label, self.filter_value(name, raw), self.url_without(path, keys))
                )
        return filters

    def filter_value(self, name, raw):
        """What a chip shows: a choice's label, or the text as typed."""
        choices = getattr(self.fields[name], "choices", None)
        if choices is None:
            return raw
        return {str(key): label for key, label in choices}.get(raw, raw)

    def url_without(self, path, keys):
        """The same search without `keys` (and back on the first page)."""
        dropped = {*keys, "page"}
        params = QueryDict(mutable=True)
        for key in self.data:
            if key not in dropped:
                params.setlist(key, [value for value in self._values(key) if value != ""])
        query = params.urlencode()
        return f"{path}?{query}" if query else path

    def _values(self, key):
        if isinstance(self.data, QueryDict):
            return self.data.getlist(key)
        return [str(self.data[key])]
