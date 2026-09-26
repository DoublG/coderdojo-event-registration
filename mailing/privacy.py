"""Personal data in mailing's models (DATA_MODEL.md §16, `privacy.registry`)."""

from privacy.registry import Category, LegalBasis, Subject, keep, personal, register, register_not_personal

from .models import (
    BounceRecord,
    Campaign,
    ConsentEvent,
    EmailMessage,
    EmailSuppression,
    EmailTemplate,
    Journey,
    JourneyDelivery,
    MailPreference,
    ProcessedImapMessage,
    Segment,
    SegmentGroup,
    SegmentRule,
)

register(
    EmailMessage,
    subjects={Subject.ACCOUNT: "user", Subject.CHILD: "user__ninja"},
    purpose="Sending mail, and the record of exactly what was sent to whom",
    legal_basis=LegalBasis.LEGITIMATE_INTEREST,
    retention="mail_content",
    seen_by="The organisation (Django admin)",
    fields={
        ("user", "recipient", "subject", "body"): personal(Category.IDENTITY),
        # Holds the account id ("campaign:<id>:<user>").
        "idempotency_key": personal(Category.IDENTITY, export=False),
        "message_id": personal(Category.IDENTITY, export=False),
        (
            "category",
            "template_key",
            "language",
            "campaign",
            "status",
            "status_reason",
            "created_at",
            "sent_at",
            "bounced_at",
            "is_test",
        ): keep(Category.IDENTITY, "mail statistics, no longer linked to the person"),
    },
    not_personal=["id", "priority", "send_after", "claimed_at", "attempts"],
)

register(
    MailPreference,
    subjects={Subject.ACCOUNT: "user", Subject.CHILD: "user__ninja"},
    purpose="Which kinds of mail the account wants",
    legal_basis=LegalBasis.CONSENT,
    retention="account",
    seen_by="The account holder; the organisation (Django admin)",
    fields={("user", "category", "subscribed", "changed_at"): personal(Category.IDENTITY)},
    not_personal=["id"],
)

register(
    ConsentEvent,
    subjects={Subject.ACCOUNT: "user", Subject.CHILD: "user__ninja"},
    purpose="Proof of every consent given or withdrawn (art. 7.1)",
    legal_basis=LegalBasis.LEGAL_OBLIGATION,
    retention="consent_proof",
    seen_by="The organisation (Django admin)",
    fields={
        ("user", "category", "subscribed", "source", "wording_version", "created_at"): keep(
            Category.IDENTITY, "proof of consent; points at the anonymised account"
        ),
    },
    not_personal=["id"],
)

register(
    EmailSuppression,
    subjects={Subject.EMAIL: "email"},
    purpose="Never mailing an address again that bounced, complained or asked not to be mailed",
    legal_basis=LegalBasis.LEGITIMATE_INTEREST,
    retention="suppression",
    seen_by="The organisation (Django admin)",
    fields={
        ("email", "reason", "note", "created_at"): keep(
            Category.IDENTITY, "without it, the address would be mailed again"
        ),
    },
    not_personal=["id"],
)

register(
    BounceRecord,
    purpose="Handling mail that couldn't be delivered",
    legal_basis=LegalBasis.LEGITIMATE_INTEREST,
    retention="mail_log",
    seen_by="The organisation (Django admin)",
    fields={
        ("email", "kind", "status_code", "diagnostic", "message", "created_at"): personal(
            Category.IDENTITY, export=False
        ),
    },
    not_personal=["id"],
)

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
    purpose="Who launched a campaign",
    legal_basis=LegalBasis.LEGITIMATE_INTEREST,
    retention="account",
    seen_by="The organisation",
    fields={"launched_by": keep(Category.IDENTITY, "points at the anonymised account", export=False)},
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
    ],
)

# Segments describe an audience by its attributes, never by naming a person.
for model in (Segment, SegmentGroup, SegmentRule, Journey):
    register_not_personal(model, "describes an audience, never a person")
register_not_personal(EmailTemplate, "the mail texts, before any personal detail is filled in")
register_not_personal(ProcessedImapMessage, "which bounce-mailbox messages were handled, by mailbox and id")
