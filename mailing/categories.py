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
