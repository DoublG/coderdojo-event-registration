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

from django import forms
from django.forms.renderers import TemplatesSetting
from django.forms.widgets import Input

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
