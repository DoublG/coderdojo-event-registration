"""Personal data in events' models (DATA_MODEL.md §16, `privacy.registry`)."""

from privacy.registry import Category, LegalBasis, Subject, keep, personal, register, register_not_personal

from .models import (
    Badge,
    Belt,
    Event,
    NinjaBadge,
    NinjaBelt,
    NinjaEngagement,
    NinjaEngagementChange,
    Registration,
    RegistrationCancellation,
    TeamAttendance,
)

FAMILY_AND_TEAM = "The family; the dojo's team; the organisation (Django admin)"
ANONYMISED_CHILD = "points at the anonymised child, so the session's numbers stay right"

register(
    Event,
    purpose="Who runs a session",
    legal_basis=LegalBasis.LEGITIMATE_INTEREST,
    retention="team",
    seen_by="The dojo's team; the organisation",
    fields={
        "team": keep(Category.IDENTITY, "memberships are kept with an anonymised account"),
        "ninjas": keep(Category.CHILD, ANONYMISED_CHILD, retention="registration"),
    },
    not_personal=[
        "id",
        "translations",
        "name",
        "dojo",
        "status",
        "start_time",
        "end_time",
        "places",
        "location",
        "venue_name",
        "image",
        "description",
        "min_age",
        "max_age",
        "audience",
        "external_registration_url",
        "published_at",
        "announced_at",
        "pathways",
    ],
)

register(
    Registration,
    subjects={Subject.CHILD: "ninja"},
    purpose="Signing a child up for a session, the waiting list and attendance",
    legal_basis=LegalBasis.CONTRACT,
    retention="registration",
    seen_by=FAMILY_AND_TEAM,
    fields={
        ("ninja", "waiting_list", "position", "attended", "created_at", "pathways"): keep(
            Category.CHILD, ANONYMISED_CHILD
        ),
    },
    not_personal=["id", "event"],
)

register(
    RegistrationCancellation,
    subjects={Subject.CHILD: "ninja"},
    purpose="Keeping track of cancelled places, for mail targeting and planning places",
    legal_basis=LegalBasis.LEGITIMATE_INTEREST,
    retention="registration",
    seen_by="The organisation",
    fields={
        ("ninja", "was_waitlisted", "signed_up_at", "cancelled_at"): personal(Category.CHILD),
        "cancelled_by": personal(Category.IDENTITY),
    },
    not_personal=["id", "event"],
)

AWARDED = dict(
    legal_basis=LegalBasis.CONTRACT,
    retention="child",
    seen_by="The family; the teams of the dojos the child goes to; the organisation",
)

register(
    NinjaBadge,
    subjects={Subject.CHILD: "ninja"},
    purpose="The badges a child earned",
    fields={
        ("ninja", "earned_date", "progress_current", "progress_total", "note"): personal(Category.CHILD),
        ("awarded_by", "awarded_as_membership"): keep(Category.IDENTITY, "points at the anonymised account"),
    },
    not_personal=["id", "badge"],
    **AWARDED,
)

register(
    NinjaBelt,
    subjects={Subject.CHILD: "ninja"},
    purpose="A child's belts (their coding level), an append-only history",
    fields={
        ("ninja", "awarded_on", "note"): personal(Category.CHILD),
        ("awarded_by", "awarded_as_membership", "awarded_as_role"): keep(
            Category.IDENTITY, "points at the anonymised account"
        ),
    },
    not_personal=["id", "belt"],
    **AWARDED,
)

ENGAGEMENT = dict(
    purpose="How a child comes to sessions: shown to the dojo team, and used to choose who gets which mail",
    legal_basis=LegalBasis.LEGITIMATE_INTEREST,
    retention="engagement",
    seen_by="The dojo's team (the child's stage there); the organisation, through mail segments",
)

register(
    NinjaEngagement,
    subjects={Subject.CHILD: "ninja"},
    fields={
        (
            "ninja",
            "stage",
            "first_attended",
            "last_attended",
            "attended_total",
            "attended_180d",
            "offered_180d",
            "attendance_rate",
            "missed_in_a_row",
            "no_shows_90d",
            "has_upcoming",
            "from_marked_attendance",
            "computed_on",
            "main_dojo",
        ): personal(Category.PROFILING),
    },
    not_personal=["id", "dojo"],
    **ENGAGEMENT,
)

register(
    NinjaEngagementChange,
    subjects={Subject.CHILD: "ninja"},
    fields={("ninja", "from_stage", "to_stage", "changed_on"): personal(Category.PROFILING)},
    not_personal=["id"],
    **ENGAGEMENT,
)

register(
    TeamAttendance,
    subjects={Subject.ACCOUNT: "membership__user", Subject.CHILD: "membership__user__ninja"},
    purpose="Who of the team was at a session: the record the insurance needs",
    legal_basis=LegalBasis.LEGITIMATE_INTEREST,
    retention="team_attendance",
    seen_by="The dojo's team; the organisation",
    fields={
        ("membership", "attended", "marked_at"): keep(Category.IDENTITY, "the insurance record of who was there"),
        "marked_by": keep(Category.IDENTITY, "points at the anonymised account", export=False),
    },
    not_personal=["id", "event"],
)

register_not_personal(Belt, "the organisation's belt catalogue")
register_not_personal(Badge, "the organisation's badge catalogue")
