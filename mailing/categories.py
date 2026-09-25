"""Mail categories: what a mail is about, and so whether its recipient can
opt out of it (DATA_MODEL.md §11, "Mail categories"). A code enum rather
than a table: adding a category is a code change.

Preferences per account (MailPreference) aren't built yet; CAN_OPT_OUT and
DEFAULT_SUBSCRIBED already record the agreed rules for when they are.
"""

from django.db import models


class MailCategory(models.TextChoices):
    SERVICE = "service", "Account and security"
    REGISTRATION = "registration", "Session bookings"
    REMINDER = "reminder", "Reminders"
    DOJO_NEWS = "dojo_news", "News from your dojo"
    VOLUNTEER = "volunteer", "Volunteering"
    NEWSLETTER = "newsletter", "Newsletter and campaigns"


# service/registration mail is about the account or a booking the recipient
# made, so it can't be switched off (a hard bounce still stops it).
CAN_OPT_OUT = {
    MailCategory.SERVICE: False,
    MailCategory.REGISTRATION: False,
    MailCategory.REMINDER: True,
    MailCategory.DOJO_NEWS: True,
    MailCategory.VOLUNTEER: True,
    MailCategory.NEWSLETTER: True,
}

# What applies while an account hasn't made a choice. The newsletter always
# needs an explicit opt-in; reminders and dojo news are on by default
# (decided 2026-09-25).
DEFAULT_SUBSCRIBED = {
    MailCategory.SERVICE: True,
    MailCategory.REGISTRATION: True,
    MailCategory.REMINDER: True,
    MailCategory.DOJO_NEWS: True,
    MailCategory.VOLUNTEER: True,
    MailCategory.NEWSLETTER: False,
}

# A ninja's own login (with an email) only gets mail about its own
# bookings and its dojo; campaigns and the newsletter go to adults only
# (DATA_MODEL.md §11, decisions).
ALLOWED_FOR_NINJA_ACCOUNTS = {
    MailCategory.SERVICE,
    MailCategory.REGISTRATION,
    MailCategory.REMINDER,
    MailCategory.DOJO_NEWS,
}

# Lower goes first: the dispatcher claims pending mail in this order, so a
# password reset never waits behind a campaign.
PRIORITY = {
    MailCategory.SERVICE: 0,
    MailCategory.REGISTRATION: 1,
    MailCategory.REMINDER: 5,
    MailCategory.DOJO_NEWS: 5,
    MailCategory.VOLUNTEER: 5,
    MailCategory.NEWSLETTER: 9,
}

# Which version of the privacy explanation (DATA_MODEL.md §11, "Sending
# pipeline" step 5) a consent was given under; recorded on ConsentEvent.
PRIVACY_WORDING_VERSION = "2026-09-25"


def categories_for(user):
    """The categories `user` can receive at all."""
    if user.is_ninja:
        return [c for c in MailCategory if c in ALLOWED_FOR_NINJA_ACCOUNTS]
    return list(MailCategory)

# One line per category for the Mail preferences page.
DESCRIPTIONS = {
    MailCategory.SERVICE: "Password resets, background-check requests and other mail about your account.",
    MailCategory.REGISTRATION: "Confirmations and changes for the sessions you signed up for.",
    MailCategory.REMINDER: "A reminder two days before a session you signed up for.",
    MailCategory.DOJO_NEWS: "New sessions and news from the dojos your family goes to.",
    MailCategory.VOLUNTEER: "News for champions and mentors, and calls for volunteers.",
    MailCategory.NEWSLETTER: "The CoderDojo Belgium newsletter and events like Coolest Projects and CoderDojo Girlz.",
}
