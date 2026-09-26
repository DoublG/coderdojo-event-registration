"""A guardian's consent to the children's data being kept (DATA_MODEL.md
§16). The approved wording is accounts/partials/_child_data_consent.html,
the checkbox on family sign-up and on Add a child; change it only together
with CHILD_DATA_WORDING_VERSION. Every guardianship made on the site records
when the consent was given and to which wording."""

from django.utils import timezone

CHILD_DATA_WORDING_VERSION = "2026-09-26"


def consent_fields():
    """The Guardianship fields recording a consent given now."""
    return {"consent_given_at": timezone.now(), "consent_wording_version": CHILD_DATA_WORDING_VERSION}
