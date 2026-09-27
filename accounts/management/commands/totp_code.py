from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django_otp.oath import totp
from django_otp.plugins.otp_totp.models import TOTPDevice


class Command(BaseCommand):
    help = (
        "Print the code an account's authenticator app shows right now, to log in to a seeded account with "
        "two-step login (seed_two_step) without an app. DEBUG only."
    )

    def add_arguments(self, parser):
        parser.add_argument("username")

    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError("Only with DEBUG on: this prints a login code.")
        device = TOTPDevice.objects.filter(user__username=options["username"], confirmed=True).first()
        if device is None:
            raise CommandError(f"{options['username']} has no authenticator app.")
        code = totp(device.bin_key, device.step, device.t0, device.digits, device.drift)
        self.stdout.write(str(code).zfill(device.digits))
