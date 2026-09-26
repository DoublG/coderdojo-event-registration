"""Personal data in dojos' models (DATA_MODEL.md §16, `privacy.registry`)."""

from privacy.registry import Category, LegalBasis, Subject, keep, personal, register

from .models import Dojo, DojoMembership

register(
    Dojo,
    purpose="A dojo's public page and how families reach it",
    legal_basis=LegalBasis.LEGITIMATE_INTEREST,
    retention="published",
    seen_by="Everyone, while the dojo is active; its team; the organisation",
    fields={
        # Often the champion's own address or number.
        ("email", "phone", "address", "location"): personal(Category.CONTACT_PUBLIC),
        "created_by": keep(Category.IDENTITY, "points at the anonymised account of the dojo's founder"),
    },
    not_personal=[
        "id",
        "translations",
        "name",
        "municipality",
        "province",
        "status",
        "kind",
        "icon",
        "tagline",
        "description",
        "schedule_description",
        "min_age",
        "max_age",
        "visit_notes",
        "languages",
        "pathways",
    ],
)

register(
    DojoMembership,
    subjects={Subject.ACCOUNT: "user", Subject.CHILD: "user__ninja"},
    purpose="Who is on a dojo's team, in which role, and who ran past sessions",
    legal_basis=LegalBasis.LEGITIMATE_INTEREST,
    retention="team",
    seen_by="The dojo's team; everyone for a profile shown on the team pages; the organisation",
    fields={
        # Kept with the anonymised account: past sessions' teams (Event.team)
        # and awarded belts point at the membership.
        ("user", "role", "status", "joined_at", "left_at", "created_at"): keep(
            Category.IDENTITY, "past sessions' teams and awards point at it; the account is anonymised"
        ),
        ("requested_by", "decided_by"): keep(Category.IDENTITY, "points at the anonymised account", export=False),
        "promoted_by": keep(
            Category.IDENTITY, "points at a membership, itself kept with an anonymised account", export=False
        ),
    },
    not_personal=["id", "dojo"],
)
