"""The standard reports that come with the site (DATA_MODEL_REPORTS.md §30):
published and shared with every dojo, installed by `manage.py
load_standard_reports` on every deploy (scripts/deploy.sh) and dev start.

The command creates a missing one, and brings one up to date with the code
while the row is still exactly as it installed it (its `standard_hash`
matches); a report an admin has edited is theirs and stays as it is. Settings
are stored the way reports.config stores them: columns as `col:<key>`,
translated values as `val:<key>`. The names and descriptions are translated
on the pages (Report.label) for as long as the row is unchanged."""

import hashlib
import json
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from django.utils.functional import Promise
from django.utils.translation import gettext_lazy as _

if TYPE_CHECKING:
    from .models import Report


@dataclass(frozen=True)
class StandardReport:
    key: str
    name: str | Promise
    description: str | Promise
    dataset: str
    config: dict[str, Any] = field(default_factory=dict)
    position: int = 0


STANDARD_REPORTS: dict[str, StandardReport] = {
    report.key: report
    for report in (
        StandardReport(
            key="children_per_stage",
            name=_("Children per engagement stage"),
            description=_("How many children are regular, occasional, new, at risk or lapsed."),
            dataset="engagement",
            config={"plugin": "Y Bar", "group_by": ["col:stage"], "columns": ["col:ninjas"]},
            position=10,
        ),
        StandardReport(
            key="children_per_age_and_gender",
            name=_("Children per age band and gender"),
            description=_("How many children of each age band come, split by gender."),
            dataset="engagement",
            config={
                "plugin": "Y Bar",
                "group_by": ["col:age_band"],
                "split_by": ["col:gender"],
                "columns": ["col:ninjas"],
            },
            position=20,
        ),
        StandardReport(
            key="regular_and_lapsed",
            name=_("Regular and lapsed children"),
            description=_(
                "Regular children next to those who stopped coming, with the sessions they came to and were "
                "offered in the last 180 days."
            ),
            dataset="engagement",
            config={
                "plugin": "Datagrid",
                "group_by": ["col:stage"],
                "columns": ["col:ninjas", "col:attended_180d", "col:offered_180d"],
                "filter": [["col:stage", "in", ["val:regular", "val:lapsed"]]],
            },
            position=30,
        ),
    )
}


def fingerprint(report: "Report | StandardReport") -> str:
    """What load_standard_reports compares: name, description and settings."""
    data = json.dumps([str(report.name), str(report.description), report.config], sort_keys=True)
    return hashlib.sha256(data.encode()).hexdigest()


def install() -> dict[str, int]:
    """Create the missing standard reports and update the unchanged ones.
    Safe to run twice; returns how many were created and updated."""
    from django.utils import translation

    from .models import Report

    created = updated = 0
    # The rows hold the English text; the pages translate it (Report.label).
    with translation.override("en-us"):
        for definition in STANDARD_REPORTS.values():
            fields = {
                "name": str(definition.name),
                "description": str(definition.description),
                "dataset": definition.dataset,
                "config": definition.config,
            }
            new_hash = fingerprint(definition)
            report = Report.objects.filter(standard_key=definition.key).first()
            if report is None:
                Report.objects.create(
                    standard_key=definition.key,
                    standard_hash=new_hash,
                    status=Report.PUBLISHED,
                    shared_with_dojos=True,
                    position=definition.position,
                    **fields,
                )
                created += 1
            elif report.standard_hash != new_hash and fingerprint(report) == report.standard_hash:
                for name, value in fields.items():
                    setattr(report, name, value)
                report.standard_hash = new_hash
                report.save()
                updated += 1
    return {"created": created, "updated": updated}
