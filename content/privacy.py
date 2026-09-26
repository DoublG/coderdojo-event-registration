"""Personal data in content's models (DATA_MODEL.md §16, `privacy.registry`)."""

from privacy.registry import Category, LegalBasis, Subject, personal, register, register_not_personal

from .models import FAQ, Announcement, OrganisationTeamMember, Promotion, Sponsor, Testimonial

register(
    Testimonial,
    purpose="A quote from a family or volunteer, on the public site",
    legal_basis=LegalBasis.CONSENT,
    retention="published",
    seen_by="Everyone",
    fields={
        # translations holds the quote and role in the other languages.
        ("author", "role", "quote", "translations"): personal(Category.PUBLIC_PROFILE),
    },
    not_personal=["id", "dojo"],
)

register(
    OrganisationTeamMember,
    subjects={Subject.ACCOUNT: "account"},
    visible_when="is_public",
    purpose="The organisation's team listing on the public site",
    legal_basis=LegalBasis.CONSENT,
    retention="published",
    seen_by="Everyone, while is_public is on; the organisation",
    fields={
        (
            "name",
            "position",
            "email",
            "bio",
            "photo",
            "focus_areas",
            "joined_date",
            "is_public",
            "account",
            "translations",
        ): personal(Category.PUBLIC_PROFILE),
    },
    not_personal=["id", "order"],
)

register_not_personal(FAQ, "questions and answers written by the organisation or a dojo")
register_not_personal(Announcement, "a dojo's news notes")
register_not_personal(Promotion, "featured events")
register_not_personal(Sponsor, "sponsoring companies")
