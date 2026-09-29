"""The security mails about a login (DATA_MODEL.md §15, §24): two-step login
turned on or off, a method added or removed, a backup code used, the login
method changed. They go to the account itself; for a ninja's own login the
guardians get a notice too (`child_login_changed`), since the login is
theirs to give and take away (§17)."""

from django.conf import settings
from django.urls import reverse

from mailing.categories import MailCategory
from mailing.services import send_or_log

# What changed on a child's login, for the guardians' notice (the template's
# `change` variable).
TWO_STEP_ON = "two_step_turned_on"
TWO_STEP_METHOD_ADDED = "two_step_method_added"
TWO_STEP_METHOD_REMOVED = "two_step_method_removed"
TWO_STEP_OFF = "two_step_turned_off"
BACKUP_CODE_USED = "backup_code_used"
LOGIN_METHOD_CHANGED = "login_method_changed"
EMAIL_CHANGED = "email_changed"


def security_url():
    return settings.SITE_URL + reverse("account_security")


def send_security_mail(user, key, change=None, **context):
    """Mail `key` to `user` (when it has an address), and for a ninja's own
    login tell its guardians what changed (`change`, defaults to `key`)."""
    if user.email:
        send_or_log(user, MailCategory.SERVICE, key, {"security_url": security_url(), **context})
    tell_guardians(user, change or key, **context)


def tell_guardians(user, change, **context):
    """For a ninja's own login: the `child_login_changed` notice to each of
    the child's guardians."""
    if not user.is_ninja:
        return
    from .models import Ninja

    ninja = Ninja.objects.filter(account=user).first()
    if ninja is None:
        return
    for guardianship in ninja.guardianships.select_related("guardian"):
        guardian = guardianship.guardian
        if not guardian.email:
            continue
        send_or_log(
            guardian,
            MailCategory.SERVICE,
            "child_login_changed",
            {
                **context,
                "change": change,
                "child_name": ninja.name,
                "child_url": settings.SITE_URL + reverse("ninja_detail", kwargs={"ninja_id": ninja.pk}),
            },
        )
