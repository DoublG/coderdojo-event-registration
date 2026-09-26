"""A guardian's consent to their child's details being used to choose which
mail the family gets (DATA_MODEL.md §16). It matters only there: the
organisation dashboard's segments (so campaigns and journeys) only count a
child whose guardian gave it (`mailing.segmentation.resolver`). Signing a
child up, their sessions, belts and badges never depend on it.

It's recorded per guardian and child, on the `Guardianship`: an optional
checkbox on family sign-up and on Add a child, and a switch per child on the
Mail preferences page, where it can be withdrawn again. The approved
wording is accounts/partials/_child_data_consent.html; change it only
together with CHILD_DATA_WORDING_VERSION. Every change goes through
`set_consent`, so the audit log records it."""

from django.utils import timezone

CHILD_DATA_WORDING_VERSION = "2026-09-26b"


def consent_fields(given=True):
    """The Guardianship fields for a new link, with or without the consent."""
    if not given:
        return {}
    return {"consent_given_at": timezone.now(), "consent_wording_version": CHILD_DATA_WORDING_VERSION}


def has_consent(guardianship):
    return guardianship.consent_given_at is not None


def set_consent(guardianship, given):
    """Give or withdraw the consent for this guardian and child. Returns
    whether anything changed."""
    if given == has_consent(guardianship):
        return False
    if given:
        guardianship.consent_given_at = timezone.now()
        guardianship.consent_wording_version = CHILD_DATA_WORDING_VERSION
    else:
        guardianship.consent_given_at = None
        guardianship.consent_wording_version = ""
    guardianship.save(update_fields=["consent_given_at", "consent_wording_version"])
    return True
