"""The database's size now and projected (monitoring.capacity, CAPACITY.md),
as Markdown. Read-only, safe on production:

    manage.py capacity_report                    # now + every scenario at 1, 3 and 5 years
    manage.py capacity_report --scenario growth --years 1 2 3 4 5
    manage.py capacity_report --measure          # on a seed_scale database: store the bytes per row
"""

import json

from django.core.management.base import BaseCommand, CommandError
from django.db import connection

from monitoring import capacity, collect

MB = 1024 * 1024


def mb(value):
    return f"{value / MB:,.1f} MB" if value < 1024 * MB else f"{value / MB / 1024:,.2f} GB"


class Command(BaseCommand):
    help = "The database's size now and projected per scenario (CAPACITY.md)."

    def add_arguments(self, parser):
        parser.add_argument("--scenario", choices=sorted(capacity.SCENARIOS), action="append")
        parser.add_argument("--years", type=int, nargs="+", default=[1, 3, 5])
        parser.add_argument("--top", type=int, default=15, help="How many of the largest tables to list.")
        parser.add_argument(
            "--measure",
            action="store_true",
            help=f"Store this database's bytes per row in {capacity.ROW_SIZES_FILE.name}.",
        )

    def handle(self, *args, **options):
        tables = collect.database_tables()
        if options["measure"]:
            return self.measure(tables)
        sizes = capacity.load_row_sizes()
        self.current(tables, options["top"])
        for name in options["scenario"] or capacity.SCENARIOS:
            self.projection(capacity.SCENARIOS[name], options["years"], tables, sizes)

    def measure(self, tables):
        with connection.cursor() as cursor:
            # The table name is a constant of ours, not input.
            cursor.execute(f"SELECT AVG(LENGTH(subject) + LENGTH(body)) FROM {capacity.MAIL_TABLE}")  # noqa: S608
            mail_content = round(cursor.fetchone()[0] or 0)
        sizes = capacity.measure_row_sizes(tables, mail_content)
        if not sizes["tables"]:
            raise CommandError(f"No table has {capacity.MIN_ROWS_TO_MEASURE} rows: run seed_scale first.")
        capacity.ROW_SIZES_FILE.write_text(json.dumps(sizes, indent=2) + "\n")
        self.stdout.write(f"Stored the bytes per row of {len(sizes['tables'])} tables in {capacity.ROW_SIZES_FILE}.")
        self.stdout.write("| Table | Rows | Bytes per row |\n|---|---:|---:|")
        for name, per_row in sorted(sizes["tables"].items(), key=lambda item: -tables[item[0]]["rows"]):
            self.stdout.write(f"| `{name}` | {tables[name]['rows']:,} | {per_row:,} |")
        self.stdout.write(f"\nMail subject and body: {mail_content:,} bytes on average.")

    def current(self, tables, top):
        total = sum(t["data_bytes"] + t["index_bytes"] for t in tables.values())
        self.stdout.write(f"## This database now: {mb(total)} in {len(tables)} tables\n")
        self.stdout.write("| Table | Rows | Size |\n|---|---:|---:|")
        largest = sorted(tables.items(), key=lambda item: -(item[1]["data_bytes"] + item[1]["index_bytes"]))
        for name, t in largest[:top]:
            self.stdout.write(f"| `{name}` | {t['rows']:,} | {mb(t['data_bytes'] + t['index_bytes'])} |")
        self.stdout.write("")

    def projection(self, scenario, years, tables, sizes):
        self.stdout.write(
            f"## Scenario `{scenario.name}`: {scenario.dojos} dojos, {scenario.families:,} families, "
            f"{scenario.sessions:,} sessions, {scenario.bookings:,} bookings, {scenario.mail_per_year:,} mails a year\n"
        )
        header = " | ".join(f"after {n} year{'s' if n > 1 else ''}" for n in years)
        self.stdout.write(f"| | {header} |\n|---|{'---:|' * len(years)}")
        runs = {n: capacity.project(scenario, n, tables, sizes) for n in years}
        cleared = {n: capacity.project(scenario, n, tables, sizes, clear_mail_content=True) for n in years}
        largest = sorted(capacity.GROWTH, key=lambda table: -runs[years[-1]][table])[:8]
        for table in largest:
            self.stdout.write(f"| `{table}` | " + " | ".join(mb(runs[n][table]) for n in years) + " |")
        self.stdout.write("| **Total** | " + " | ".join(f"**{mb(sum(runs[n].values()))}**" for n in years) + " |")
        self.stdout.write(
            "| Total, mail content cleared after 12 months | "
            + " | ".join(mb(sum(cleared[n].values())) for n in years)
            + " |\n\n"
        )
