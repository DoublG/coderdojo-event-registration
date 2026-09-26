"""Personal data in applications' models (DATA_MODEL.md §16, `privacy.registry`)."""

from privacy.registry import Category, LegalBasis, Subject, keep, personal, register

from .models import Application, BackgroundCheckHistory

register(
    Application,
    subjects={Subject.ACCOUNT: "account"},
    purpose="Applying to become a champion or mentor",
    legal_basis=LegalBasis.LEGITIMATE_INTEREST,
    retention="application",
    seen_by="The applicant; the organisation's reviewers; the dojo's team for a mentor application naming it",
    fields={
        (
            "account",
            "kind",
            "status",
            "submitted_at",
            "decided_at",
            "mentor_role",
            "area",
            "preferred_schedule",
            "proposed_venue",
            "message",
            "consent",
            "background_check_consent",
        ): personal(Category.IDENTITY),
        "decided_by": keep(Category.IDENTITY, "points at the anonymised account of the reviewer", export=False),
    },
    not_personal=["id", "dojo"],
)

register(
    BackgroundCheckHistory,
    subjects={Subject.ACCOUNT: "account"},
    purpose="The audit log of background-check decisions (never the document itself)",
    legal_basis=LegalBasis.LEGITIMATE_INTEREST,
    retention="background_check",
    seen_by="The organisation's background-check reviewers; the organisation (Django admin)",
    fields={
        ("account", "decision", "reviewed_at", "requested_at", "submitted_at", "expires_at", "note"): keep(
            Category.CRIMINAL, "proof of which checks were done, for as long as the legal rules say"
        ),
        "reviewed_by": keep(Category.IDENTITY, "points at the anonymised account of the reviewer", export=False),
    },
    not_personal=["id"],
)
