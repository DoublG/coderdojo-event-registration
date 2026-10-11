"""Personal data in the reports app's models (DATA_MODEL.md §16, `core.privacy_registry`)."""

from core.privacy_registry import Category, LegalBasis, keep, register

from .models import Report

register(
    Report,
    purpose="Who made and last changed a saved report",
    legal_basis=LegalBasis.LEGITIMATE_INTEREST,
    retention="account",
    seen_by="The organisation",
    fields={("created_by", "updated_by"): keep(Category.IDENTITY, "points at the anonymised account", export=False)},
    not_personal=["id", "name", "description", "dataset", "config", "created_at", "updated_at"],
)
