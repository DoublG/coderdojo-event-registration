"""Personal data in mailing's models (DATA_MODEL.md §16, `core.privacy_registry`)."""

from core.privacy_registry import Category, LegalBasis, Subject, keep, personal, register, register_not_personal

from .models import (
    BounceRecord,
    ConsentEvent,
    DojoMailMute,
    EmailMessage,
    EmailSuppression,
    EmailTemplate,
    MailPreference,
    ProcessedImapMessage,
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
            "dojo",
            "reply_to",
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
    DojoMailMute,
    subjects={Subject.ACCOUNT: "user", Subject.CHILD: "user__ninja"},
    purpose="Which dojos' news the account doesn't want",
    legal_basis=LegalBasis.CONSENT,
    retention="account",
    seen_by="The account holder; the organisation (Django admin)",
    fields={("user", "dojo", "created_at"): personal(Category.IDENTITY)},
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
        ("user", "category", "dojo", "subscribed", "source", "wording_version", "created_at"): keep(
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

register_not_personal(EmailTemplate, "the mail texts, before any personal detail is filled in")
register_not_personal(ProcessedImapMessage, "which bounce-mailbox messages were handled, by mailbox and id")
