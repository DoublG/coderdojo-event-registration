"""How big the database gets (CAPACITY.md, "Database growth"): a model of
how many rows each table gains per year from a few volumes (dojos, families,
sessions, bookings, mail), times the bytes a row takes.

The bytes per row are measured, never guessed: `manage.py seed_scale` fills
a separate database with a year of realistic data, and `manage.py
capacity_report --measure` stores what each row takes there in
`row_sizes.json`. The row counts per year are the formulas in `GROWTH`,
each a best estimate from how the site works (which actions write which
rows); change them when real figures say otherwise."""

import json
from dataclasses import asdict, dataclass
from pathlib import Path

ROW_SIZES_FILE = Path(__file__).with_name("row_sizes.json")
# A table without a measured size, or with too few rows to measure (InnoDB's
# smallest allocation is a 16 KB page), counts this per row.
DEFAULT_ROW_BYTES = 400
MIN_ROWS_TO_MEASURE = 1000
MAIL_TABLE = "mailing_emailmessage"


@dataclass(frozen=True)
class Scenario:
    """The volumes of one year. `families` are the adult accounts with
    children; `new_family_share` of them sign up each year (accounts are
    anonymised after two years without a login, never deleted, so the
    tables still grow by every new family)."""

    name: str
    dojos: int
    families: int
    sessions_per_dojo: int
    bookings_per_session: int
    children_per_family: float = 1.5
    guardians_per_child: float = 1.3
    team_per_session: int = 4
    new_family_share: float = 0.35
    # Mail per family per year beyond the bookings' own confirmations and
    # reminders: new-sessions digests, the organisation's campaigns and
    # journeys, and the dojos' own mailings.
    digests_per_family: int = 6
    campaigns_per_family: int = 6
    dojo_mailings_per_family: int = 6
    journeys_per_family: int = 1

    @property
    def sessions(self):
        return self.dojos * self.sessions_per_dojo

    @property
    def bookings(self):
        return self.sessions * self.bookings_per_session

    @property
    def children(self):
        return round(self.families * self.children_per_family)

    @property
    def new_families(self):
        return round(self.families * self.new_family_share)

    @property
    def mail_per_year(self):
        return round(sum(mail_breakdown(self).values()))


# Three sizes to plan for. "today" is roughly CoderDojo Belgium's current
# reach; the other two are what growth would look like.
SCENARIOS = {
    "today": Scenario("today", dojos=60, families=3000, sessions_per_dojo=10, bookings_per_session=15),
    "growth": Scenario("growth", dojos=100, families=6000, sessions_per_dojo=12, bookings_per_session=20),
    "stretch": Scenario("stretch", dojos=150, families=12000, sessions_per_dojo=20, bookings_per_session=25),
}


def mail_breakdown(s):
    """Mails per year by what sends them (mailing.automated, campaigns, journeys)."""
    booked = s.bookings * 1.1  # plus the waiting list, about a tenth more
    return {
        "booking confirmations and waiting-list mail": booked * s.guardians_per_child,
        "session reminders": s.bookings * s.guardians_per_child,
        "new-sessions digests": s.families * s.digests_per_family,
        "organisation campaigns": s.families * s.campaigns_per_family,
        "dojo mailings": s.families * s.dojo_mailings_per_family,
        "journeys": s.families * s.journeys_per_family,
        "account mail (sign-up, logins, resets)": s.new_families * 3 + s.families * 0.5,
    }


def _audit_entries(s):
    """Audit log entries per year (core.audit.RECORDED): a booking is created,
    marked and sometimes cancelled; a session is created, edited and its
    team marked; a new family writes its account, children, guardianships,
    preferences and consents; belts and badges are awarded."""
    return (
        s.bookings * 1.1 * 2
        + s.bookings * 0.15
        + s.sessions * (3 + s.team_per_session)
        + s.new_families * (1 + s.children_per_family * 2 + 12)
        + s.children * 1.9
    )


# table: (kind, rows(scenario)). "yearly" rows are added every year and
# kept; "level" rows stay about that many however long the site runs
# (rebuilt, expired or bounded by the people active now).
GROWTH = {
    "events_event": ("yearly", lambda s: s.sessions),
    "events_event_team": ("yearly", lambda s: s.sessions * s.team_per_session),
    "events_event_pathways": ("yearly", lambda s: s.sessions * 2),
    "events_teamattendance": ("yearly", lambda s: s.sessions * s.team_per_session),
    "events_registration": ("yearly", lambda s: s.bookings * 1.1),
    "events_registration_pathways": ("yearly", lambda s: s.bookings * 1.1 * 1.2),
    "events_registrationcancellation": ("yearly", lambda s: s.bookings * 0.15),
    "events_ninjabadge": ("yearly", lambda s: s.children * 1.5),
    "events_ninjabelt": ("yearly", lambda s: s.children * 0.4),
    "events_ninjaengagementchange": ("yearly", lambda s: s.children * 3),
    "events_ninjaengagement": ("level", lambda s: s.children * 2.2),
    "accounts_user": ("yearly", lambda s: s.new_families),
    "accounts_ninja": ("yearly", lambda s: s.new_families * s.children_per_family),
    "accounts_guardianship": ("yearly", lambda s: s.new_families * s.children_per_family * s.guardians_per_child),
    "mailing_mailpreference": ("yearly", lambda s: s.new_families * 1.5),
    "mailing_consentevent": ("yearly", lambda s: s.new_families * 6 + s.families * 0.2),
    "mailing_emailmessage": ("yearly", lambda s: s.mail_per_year),
    "mailing_journeydelivery": ("yearly", lambda s: s.families * s.journeys_per_family),
    "mailing_bouncerecord": ("yearly", lambda s: s.mail_per_year * 0.01),
    "mailing_processedimapmessage": ("yearly", lambda s: s.mail_per_year * 0.01),
    "auditlog_logentry": ("yearly", _audit_entries),
    "notifications_notification": ("yearly", lambda s: s.sessions * 2),
    "django_session": ("level", lambda s: s.families * 0.3),
}


def load_row_sizes():
    try:
        return json.loads(ROW_SIZES_FILE.read_text())
    except FileNotFoundError:
        return {"tables": {}, "mail_content_bytes": 0}


def measure_row_sizes(tables, mail_content_bytes):
    """Bytes per row (data plus indexes) of each table with enough rows to
    tell, from `collect.database_tables()`."""
    return {
        "tables": {
            name: round((t["data_bytes"] + t["index_bytes"]) / t["rows"])
            for name, t in sorted(tables.items())
            if t["rows"] >= MIN_ROWS_TO_MEASURE
        },
        "mail_content_bytes": mail_content_bytes,
    }


def row_bytes(table, sizes, current=None):
    measured = sizes["tables"].get(table)
    if measured:
        return measured
    if current and current.get("rows", 0) >= MIN_ROWS_TO_MEASURE:
        return (current["data_bytes"] + current["index_bytes"]) / current["rows"]
    return DEFAULT_ROW_BYTES


def project(scenario, years, current_tables, sizes, clear_mail_content=False):
    """{table: bytes} after `years` more years of `scenario`, on top of what
    every table holds now. With `clear_mail_content`, mail older than a year
    keeps its row but not its subject and body (the `mail_content`
    retention rule in core.privacy_registry, not yet applied by the retention
    job)."""
    result = {}
    for table, (kind, rows_per_year) in GROWTH.items():
        current = current_tables.get(table, {})
        now = current.get("data_bytes", 0) + current.get("index_bytes", 0)
        per_row = row_bytes(table, sizes, current)
        if kind == "yearly":
            size = now + rows_per_year(scenario) * years * per_row
        else:
            size = max(now, rows_per_year(scenario) * per_row)
        if table == MAIL_TABLE and clear_mail_content and years > 1:
            older = rows_per_year(scenario) * (years - 1)
            size -= older * min(sizes.get("mail_content_bytes", 0), per_row * 0.8)
        result[table] = size
    for table, t in current_tables.items():
        if table not in GROWTH:
            result[table] = t["data_bytes"] + t["index_bytes"]
    return result


def scenario_dict(scenario):
    return {
        **asdict(scenario),
        "sessions": scenario.sessions,
        "bookings": scenario.bookings,
        "mail": scenario.mail_per_year,
    }
