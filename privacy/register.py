"""The register of processing activities (GDPR art. 30, DATA_MODEL.md §16
phase 2), built from the classification in `privacy.registry` only."""

import csv
import io
from itertools import groupby

from django.utils import timezone

from privacy import registry
from privacy.registry import RETENTION_RULES, Category, Erasure, LegalBasis

CSV_COLUMNS = [
    "category",
    "model",
    "field",
    "purpose",
    "legal_basis",
    "retention",
    "seen_by",
    "on_erasure",
    "details",
    "export",
]


def rows():
    """One dict per personal field, by category (in `Category` order), then model and field."""
    order = {category: index for index, category in enumerate(Category.values)}
    result = []
    for entry in registry.registered():
        for name, spec in entry.fields.items():
            if spec.on_erasure == Erasure.ANONYMISE:
                details = f"replaced by {spec.replacement!r}"
            elif spec.on_erasure == Erasure.KEEP:
                details = spec.reason
            else:
                details = ""
            result.append(
                {
                    "category": spec.category,
                    "model": entry.label,
                    "field": name,
                    "purpose": spec.purpose,
                    "legal_basis": spec.legal_basis,
                    "retention": spec.retention,
                    "seen_by": spec.seen_by,
                    "on_erasure": spec.on_erasure,
                    "details": details,
                    "export": "yes" if spec.export else "no",
                }
            )
    result.sort(key=lambda row: (order[row["category"]], row["model"]))
    return result


def as_csv():
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=CSV_COLUMNS)
    writer.writeheader()
    writer.writerows(rows())
    return output.getvalue()


def _cell(text):
    return str(text).replace("|", "\\|").replace("\n", " ")


def _erasure(fields):
    """What erasure does to these fields: "delete", or per group of fields
    when they differ ("email, phone: delete; date_joined: keep (...)")."""
    by_outcome = {}
    for row in fields:
        outcome = Erasure(row["on_erasure"]).label.lower() + (f" ({row['details']})" if row["details"] else "")
        by_outcome.setdefault(outcome, []).append(row["field"])
    if len(by_outcome) == 1:
        return next(iter(by_outcome))
    return "; ".join(f"{', '.join(names)}: {outcome}" for outcome, names in by_outcome.items())


def as_markdown():
    """Per category, one line per model and purpose with its fields."""
    lines = [
        "# Register of processing activities",
        "",
        f"Generated from the site's privacy classification on {timezone.localdate():%Y-%m-%d} "
        "(`manage.py privacy_register`). GDPR art. 30.",
    ]
    for category, category_rows in groupby(rows(), key=lambda row: row["category"]):
        lines += [
            "",
            f"## {Category(category).label}",
            "",
            "| Data | Purpose | Legal basis | Retention | Seen by | On erasure |",
            "|---|---|---|---|---|---|",
        ]
        grouped = groupby(
            category_rows,
            key=lambda row: (row["model"], row["purpose"], row["legal_basis"], row["retention"], row["seen_by"]),
        )
        for (model, purpose, legal_basis, retention, seen_by), fields in grouped:
            fields = list(fields)
            data = f"{model}: " + ", ".join(row["field"] for row in fields)
            erasure = _erasure(fields)
            lines.append(
                "| "
                + " | ".join(
                    _cell(text) for text in (data, purpose, LegalBasis(legal_basis).label, retention, seen_by, erasure)
                )
                + " |"
            )

    lines += ["", "## Retention rules", "", "| Rule | What is kept, and for how long |", "|---|---|"]
    lines += [f"| {name} | {_cell(text)} |" for name, text in RETENTION_RULES.items()]

    lines += ["", "## No personal data", "", "| Model | Why |", "|---|---|"]
    lines += [
        f"| {entry.label} | {_cell(entry.not_personal_reason)} |"
        for entry in registry.registered()
        if entry.not_personal_reason
    ]
    return "\n".join(lines) + "\n"
