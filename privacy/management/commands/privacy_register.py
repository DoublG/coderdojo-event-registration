from django.core.management.base import BaseCommand

from privacy.register import as_csv, as_markdown


class Command(BaseCommand):
    help = "Write the register of processing activities (GDPR art. 30) from the privacy classification."

    def add_arguments(self, parser):
        parser.add_argument("--format", choices=["markdown", "csv"], default="markdown")
        parser.add_argument("--output", "-o", help="Write to this file instead of the screen.")

    def handle(self, *args, format, output, **options):
        text = as_csv() if format == "csv" else as_markdown()
        if output:
            with open(output, "w", encoding="utf-8", newline="") as file:
                file.write(text)
            self.stdout.write(self.style.SUCCESS(f"Wrote {output}"))
        else:
            self.stdout.write(text, ending="")
