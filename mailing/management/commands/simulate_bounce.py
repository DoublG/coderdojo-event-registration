import smtplib

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from mailing.models import EmailMessage
from mailing.testing import complaint_report, dsn_report


class Command(BaseCommand):
    help = (
        "Development only: send a bounce report (hard, soft or complaint) for a sent mail into the "
        "test mail server (Mailpit), so it shows in its UI and process_bounces picks it up. "
        "With --process, handle it right away instead of waiting for the next beat run."
    )

    def add_arguments(self, parser):
        parser.add_argument("message", nargs="?", type=int, help="EmailMessage id (default: the latest sent mail)")
        parser.add_argument("--kind", choices=["hard", "soft", "complaint"], default="hard")
        parser.add_argument("--process", action="store_true", help="run the bounce processor straight after")

    def handle(self, *args, message=None, kind="hard", process=False, **options):
        if not settings.DEBUG:
            raise CommandError("simulate_bounce only runs with DEBUG on (never against a real mail server).")
        if not settings.MAILING_BOUNCE_ADDRESS:
            raise CommandError("Set MAILING_BOUNCE_ADDRESS (the devcontainer does).")
        sent = EmailMessage.objects.exclude(message_id="").order_by("-sent_at", "-id")
        row = sent.filter(pk=message).first() if message else sent.first()
        if row is None:
            raise CommandError("No sent mail to bounce (send one first).")

        bounce_to = settings.MAILING_BOUNCE_ADDRESS.replace("{id}", str(row.pk))
        if kind == "complaint":
            raw = complaint_report(row.recipient, row.message_id)
        elif kind == "soft":
            raw = dsn_report(row.recipient, row.message_id, action="delayed", status="4.2.2",
                             diagnostic="smtp; 452 4.2.2 Mailbox full", to=bounce_to)
        else:
            raw = dsn_report(row.recipient, row.message_id, to=bounce_to)

        with smtplib.SMTP(settings.EMAIL_HOST, int(settings.EMAIL_PORT), timeout=settings.EMAIL_TIMEOUT) as smtp:
            smtp.sendmail("MAILER-DAEMON@mx.example.net", [bounce_to], raw)
        self.stdout.write(f"Sent a {kind} report for mail #{row.pk} ({row.recipient}) to {bounce_to}.")

        if process:
            from mailing.bounce import BounceProcessor

            handled = BounceProcessor().process()
            row.refresh_from_db()
            self.stdout.write(self.style.SUCCESS(f"Processed {handled} message(s); mail #{row.pk} is now {row.status}."))
