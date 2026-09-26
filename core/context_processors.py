from django.conf import settings


def organisation_contact(request):
    """The organisation's contact details (settings.ORGANISATION_CONTACT),
    for the footer on every page and the Contact page."""
    return {"organisation": settings.ORGANISATION_CONTACT}
