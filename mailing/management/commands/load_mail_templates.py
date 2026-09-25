from django.core.management.base import BaseCommand

from mailing.models import EmailTemplate
from mailing.seed_templates import template_rows


class Command(BaseCommand):
    help = (
        "Create the standard email templates (mailing/seed_templates.py, en/nl/fr) that don't exist "
        "yet. Never overwrites a template someone has edited. Run on every deploy (scripts/deploy.sh) "
        "so automated mail always has its templates."
    )

    def handle(self, *args, **options):
        created = 0
        for row in template_rows():
            key, language = row.pop("key"), row.pop("language")
            _template, was_created = EmailTemplate.objects.get_or_create(key=key, language=language, defaults=row)
            created += was_created
        self.stdout.write(self.style.SUCCESS(f"Mail templates: {created} created (existing ones left as they are)."))
