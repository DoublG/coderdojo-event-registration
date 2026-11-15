"""A session's registrations as a CSV file for the dojo team (planning a
room, printing a list): the children with a place and those waiting, and
their answers to the session's sign-up questions.

What it leaves out on purpose (data minimisation): health notes, the
date of birth (the age on the day of the session is enough) and the
parents' contact details (the team reaches a family through *Mail the
families*)."""

import csv
from typing import IO

from django.utils import timezone
from django.utils.translation import gettext as _

from accounts.models import age_on

from .models import Event

# A cell starting with one of these is read as a formula by a spreadsheet.
FORMULA_STARTS = ("=", "+", "-", "@", "\t", "\r")


def safe_cell(value: str) -> str:
    """`value` as a spreadsheet shows it as text, never runs it as a formula
    (a child's name is typed by a family)."""
    return "'" + value if value.startswith(FORMULA_STARTS) else value


def yes_no(value: bool | None) -> str:
    if value is None:
        return ""
    return _("Yes") if value else _("No")


def header(event: Event) -> list[str]:
    columns = [
        _("Name"),
        _("Age"),
        _("Home dojo"),
        _("Status"),
        _("Waiting list position"),
        _("Present"),
        _("Signed up on"),
    ]
    return columns + [safe_cell(question.text) for question in event.questions.all()]


def rows(event: Event) -> list[list[str]]:
    """One row per registration: the children with a place first (by
    name), then the waiting list in its order."""
    questions = list(event.questions.all())
    day = timezone.localtime(event.start_time).date()
    registrations = list(
        event.registration_set.select_related("ninja", "ninja__home_dojo")
        .prefetch_related("answers")
        .order_by("waiting_list", "position", "ninja__name", "ninja__family_name")
    )
    confirmed = sorted(
        (r for r in registrations if not r.waiting_list),
        key=lambda r: (r.ninja.name.lower(), r.ninja.family_name.lower()),
    )
    waiting = [r for r in registrations if r.waiting_list]
    result = []
    for registration in confirmed + waiting:
        ninja = registration.ninja
        answers = {answer.question_id: answer.answer for answer in registration.answers.all()}
        result.append(
            [
                safe_cell(ninja.full_name),
                str(age_on(ninja.date_of_birth, day)) if ninja.date_of_birth else "",
                safe_cell(ninja.home_dojo.name) if ninja.home_dojo else "",
                _("Waiting list") if registration.waiting_list else _("Has a place"),
                str(registration.position) if registration.waiting_list else "",
                "" if registration.waiting_list else yes_no(registration.attended),
                timezone.localtime(registration.created_at).strftime("%d/%m/%Y %H:%M"),
            ]
            + [yes_no(answers.get(question.pk)) for question in questions]
        )
    return result


def write_csv(event: Event, out: IO[str]) -> None:
    """The file's contents, UTF-8 with a byte-order mark so a spreadsheet
    opens it right."""
    out.write("\ufeff")
    writer = csv.writer(out)
    writer.writerow(header(event))
    writer.writerows(rows(event))
