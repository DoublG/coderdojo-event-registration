"""Personal data in notifications' models (DATA_MODEL.md §16, `privacy.registry`)."""

from privacy.registry import Category, LegalBasis, Subject, personal, register

from .models import Notification

register(
    Notification,
    subjects={Subject.ACCOUNT: "recipient"},
    purpose="Telling a dojo's team what needs their attention",
    legal_basis=LegalBasis.LEGITIMATE_INTEREST,
    retention="notification",
    seen_by="The recipient; the organisation (Django admin)",
    fields={
        # The text names the person it's about (a join request, a waitlisted child).
        ("recipient", "text", "url", "created_at", "read"): personal(Category.IDENTITY),
    },
    not_personal=["id", "dojo"],
)
