from django.core.management.base import BaseCommand

from accounts.home_dojo import backfill


class Command(BaseCommand):
    help = ("Give every child without a home dojo the dojo they came to most "
            "(accounts.home_dojo.backfill). Safe to rerun: a set home dojo is never changed.")

    def handle(self, *args, **options):
        self.stdout.write(f"Home dojos set: {backfill()}")
