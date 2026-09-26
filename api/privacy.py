"""Personal data in the api app (DATA_MODEL.md §16, `privacy.registry`)."""

from privacy.registry import Category, LegalBasis, Subject, keep, register

from .models import DojoApiClient

register(
    DojoApiClient,
    subjects={Subject.ACCOUNT: "created_by"},
    purpose="The apps a dojo's champion lets work for the dojo through the API",
    legal_basis=LegalBasis.LEGITIMATE_INTEREST,
    retention="team",
    seen_by="The dojo's champion; the organisation (Django admin)",
    fields={"created_by": keep(Category.IDENTITY, "who allowed the client, as long as it exists")},
    # The account is the client's technical account, never a person's.
    not_personal=["id", "dojo", "name", "scopes", "application", "account", "created_at"],
)
