"""Personal data in the campaigns app's models (DATA_MODEL.md §16, `core.privacy_registry`)."""

from core.privacy_registry import Category, LegalBasis, Subject, keep, personal, register, register_not_personal

from .models import Campaign, Journey, JourneyDelivery, Segment, SegmentGroup, SegmentRule

register(
    JourneyDelivery,
    subjects={Subject.ACCOUNT: "user"},
    purpose="Not sending a journey's mail to the same account again within its cooldown",
    legal_basis=LegalBasis.LEGITIMATE_INTEREST,
    retention="mail_content",
    seen_by="The organisation",
    fields={("user", "email", "created_at"): personal(Category.IDENTITY)},
    not_personal=["id", "journey"],
)

register(
    Campaign,
    purpose="Who wrote and launched a campaign",
    legal_basis=LegalBasis.LEGITIMATE_INTEREST,
    retention="account",
    seen_by="The organisation",
    fields={("launched_by", "created_by"): keep(Category.IDENTITY, "points at the anonymised account", export=False)},
    not_personal=[
        "id",
        "segment",
        "segment_snapshot",
        "name",
        "category",
        "template_key",
        "context",
        "status",
        "created_at",
        "scheduled_at",
        "launched_at",
        "queued_at",
        # How far the queuing got, as a position in account id order: a
        # cursor, not a link to anyone (no foreign key, never shown).
        "queued_up_to",
        # A dojo mailing (DATA_MODEL.md §25): the dojo's own text and which
        # prepared audience it went to, never a list of people.
        "dojo",
        "audience",
        "audience_params",
        "subject",
        "message",
        "translations",
    ],
)

# Segments describe an audience by its attributes, never by naming a person.
for model in (Segment, SegmentGroup, SegmentRule, Journey):
    register_not_personal(model, "describes an audience, never a person")
