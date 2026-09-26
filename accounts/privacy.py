"""Personal data in accounts' models (DATA_MODEL.md §16, `privacy.registry`)."""

from django.contrib.auth.hashers import make_password

from privacy.registry import Category, Computed, LegalBasis, Subject, anonymise, keep, personal, register

from .models import Guardianship, Ninja, OrganisationRole, User

FAMILY_AND_TEAM = (
    "The family (every guardian, and the child's own login); the team of a dojo the child signs up at; "
    "the organisation (Django admin)"
)

register(
    User,
    subjects={Subject.ACCOUNT: "pk", Subject.CHILD: "ninja"},
    visible_when="show_on_team_pages",
    purpose="The account: logging in, and reaching the person it belongs to",
    legal_basis=LegalBasis.CONTRACT,
    retention="account",
    seen_by="The account holder; the organisation (Django admin); their name also to the teams they work with",
    fields={
        # The account row stays when other rows point at it (a past
        # session's team, a belt awarded), as "Former member #id".
        "username": anonymise(Category.IDENTITY, "former-{pk}"),
        "first_name": anonymise(Category.IDENTITY, "Former member"),
        "last_name": anonymise(Category.IDENTITY, "#{pk}"),
        ("email", "phone", "postal_code", "preferred_language"): personal(Category.IDENTITY),
        "account_type": keep(Category.IDENTITY, "tells an anonymised ninja login from an adult one in statistics"),
        "date_joined": keep(Category.IDENTITY, "sign-up statistics"),
        "is_active": anonymise(Category.IDENTITY, False),
        ("is_staff", "is_superuser", "groups", "user_permissions"): anonymise(
            Category.IDENTITY,
            False,
            purpose="Access to the management side (organisation roles)",
            legal_basis=LegalBasis.LEGITIMATE_INTEREST,
        ),
        "password": anonymise(
            Category.SECURITY, Computed("an unusable password", lambda user: make_password(None)), export=False
        ),
        ("last_login", "must_change_password"): personal(Category.SECURITY),
        ("display_name", "title", "bio", "photo", "show_on_team_pages"): personal(
            Category.PUBLIC_PROFILE,
            purpose="The profile on the team pages of the dojos they're on",
            legal_basis=LegalBasis.CONSENT,
            seen_by="Everyone, while show_on_team_pages is on; otherwise the account holder and the organisation",
        ),
        (
            "background_check_status",
            "background_check_requested_at",
            "background_check_submitted_at",
            "background_check_reviewed_at",
            "background_check_expires_at",
        ): personal(
            Category.CRIMINAL,
            purpose="Letting only volunteers with a clean criminal-record extract work with children",
            legal_basis=LegalBasis.LEGITIMATE_INTEREST,
            retention="background_check",
            seen_by="The account holder; the organisation's background-check reviewers",
        ),
        # Deleted as soon as a reviewer decides; never exported.
        "background_check_document": personal(
            Category.CRIMINAL,
            export=False,
            purpose="The criminal-record extract, until a reviewer decides",
            legal_basis=LegalBasis.LEGITIMATE_INTEREST,
            retention="background_check",
            seen_by="The organisation's background-check reviewers",
        ),
        "background_check_token": personal(
            Category.SECURITY,
            export=False,
            purpose="The upload link for the criminal-record extract",
            retention="background_check",
        ),
    },
    not_personal=["id"],
)

register(
    Ninja,
    subjects={Subject.CHILD: "pk"},
    purpose="The family's children: signing them up for sessions and following their progress",
    legal_basis=LegalBasis.CONTRACT,
    retention="child",
    seen_by=FAMILY_AND_TEAM,
    fields={
        # Kept anonymised, so the sessions the child came to keep their numbers.
        "name": anonymise(Category.CHILD, "Former ninja #{pk}"),
        "gender": anonymise(Category.CHILD, "unspecified"),
        ("date_of_birth", "photo", "account"): personal(Category.CHILD),
        ("home_dojo", "member_since"): keep(Category.CHILD, "a dojo's member numbers"),
        "allergies_notes": personal(
            Category.SPECIAL,
            purpose="Keeping the child safe at a session (allergies, medical notes)",
            legal_basis=LegalBasis.CONSENT,
            seen_by=(
                "The family; the champion of a dojo, on the attendance list of a session the child has a confirmed "
                "place at; the organisation (Django admin)"
            ),
        ),
    },
    not_personal=["id"],
)

register(
    Guardianship,
    subjects={Subject.ACCOUNT: "guardian", Subject.CHILD: "ninja"},
    purpose="Who may manage a child and gets their mail",
    legal_basis=LegalBasis.CONTRACT,
    retention="child",
    seen_by="The family; the organisation (Django admin)",
    fields={
        ("guardian", "ninja", "relation", "created_at"): personal(Category.CHILD),
        # The proof of the guardian's consent to the child's data being kept.
        ("consent_given_at", "consent_wording_version"): personal(Category.CHILD, legal_basis=LegalBasis.CONSENT),
    },
    not_personal=["id"],
)

register(
    OrganisationRole,
    subjects={Subject.ACCOUNT: "account"},
    purpose="Access to the management side",
    legal_basis=LegalBasis.LEGITIMATE_INTEREST,
    retention="organisation_role",
    seen_by="The organisation (Django admin)",
    fields={("account", "role", "granted_at"): personal(Category.IDENTITY)},
    not_personal=["id"],
)
