from django.apps import AppConfig


class CoreConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'core'

    def ready(self):
        from django import forms

        from core.audit import register_models

        register_models()
        # The site's file and image uploads (core/templates/core/widgets/): Django's
        # own layout falls apart inside a .cd-form__field. The Django admin keeps
        # its own (AdminFileWidget sets its own template).
        forms.ClearableFileInput.template_name = "core/widgets/clearable_file_input.html"
