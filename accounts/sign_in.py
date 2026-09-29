"""The organisation's sign-in policy (DATA_MODEL.md §15): which roles must
use two-step login, and whether a request meets that.

The policy is `accounts.SignInRequirement`, one row per role (set on the
organisation dashboard, /manage/security/). An account's requirement is the
strongest level among the roles it holds whose `required_from` has come; a
stronger level set for a later day is `upcoming` (a notice, nothing
enforced yet). Only adult accounts are ever asked: never a ninja's own login
and never the API's technical accounts.

Where it's applied:
- `accounts.middleware.SignInRequirementMiddleware` guides people: an account
  missing the device its role needs goes to its Sign-in security page; one
  with the device but an unverified session logs in again.
- The real lock is on what the roles open: `dojos.access.require_dojo_access`,
  `accounts.organisation.require_area`, the Django admin
  (`core.admin_site.AdminSite`) and the notification WebSocket
  (`notifications.consumers`) all refuse a request that doesn't meet it.
"""

from dataclasses import dataclass, field
from datetime import date

from django.utils import timezone
from django_otp import DEVICE_ID_SESSION_KEY

from .models import OrganisationRole, SignInRequirement, User

PASSWORD = SignInRequirement.PASSWORD
TWO_STEP = SignInRequirement.TWO_STEP
PASSKEY = SignInRequirement.PASSKEY

OK = "ok"
NEEDS_SETUP = "needs_setup"  # the account lacks the device its role needs
NEEDS_VERIFY = "needs_verify"  # it has one, but this session didn't use it


@dataclass
class Requirement:
    level: str = PASSWORD
    required_from: date | None = None
    roles: list = field(default_factory=list)  # the role values that ask for it

    @property
    def level_label(self):
        return dict(SignInRequirement.LEVEL_CHOICES)[self.level]

    @property
    def role_labels(self):
        labels = dict(SignInRequirement.ROLE_CHOICES)
        return [labels[role] for role in self.roles]


def roles_of(user, among=None):
    """The SignInRequirement roles `user` holds (limited to `among`, to spare
    the queries for roles no requirement is set for)."""
    from dojos.models import DojoMembership

    if not user.is_authenticated or user.account_type != User.ADULT:
        return set()
    among = set(among if among is not None else dict(SignInRequirement.ROLE_CHOICES))
    held = set()
    if SignInRequirement.ADULT in among:
        held.add(SignInRequirement.ADULT)
    if SignInRequirement.SUPERUSER in among and user.is_superuser:
        held.add(SignInRequirement.SUPERUSER)
    if SignInRequirement.REVIEWER in among and user.has_perm("applications.can_review_background_checks"):
        held.add(SignInRequirement.REVIEWER)
    organisation = {
        SignInRequirement.ORGANISATION_ADMIN: OrganisationRole.ADMIN,
        SignInRequirement.ORGANISATION_BOARD: OrganisationRole.BOARD,
    }
    if among & organisation.keys():
        roles = set(user.organisation_roles.values_list("role", flat=True))
        held |= {role for role, value in organisation.items() if role in among and value in roles}
    team = {SignInRequirement.CHAMPION: DojoMembership.CHAMPION, SignInRequirement.MENTOR: DojoMembership.MENTOR}
    if among & team.keys():
        roles = set(
            user.dojo_memberships.filter(status=DojoMembership.ACTIVE, role__in=team.values()).values_list(
                "role", flat=True
            )
        )
        held |= {role for role, value in team.items() if role in among and value in roles}
    return held


def requirements_for(user, today=None):
    """(enforced, upcoming) Requirements for `user`: the strongest level that
    applies today (PASSWORD when none does), and a stronger one set for a
    later day, or None."""
    today = today or timezone.localdate()
    rows = list(SignInRequirement.objects.exclude(level=PASSWORD).values_list("role", "level", "required_from"))
    enforced, upcoming = Requirement(), None
    if not rows:
        return enforced, upcoming
    held = roles_of(user, among={role for role, _level, _from in rows})
    strength = SignInRequirement.strength
    for role, level, required_from in rows:
        if role not in held:
            continue
        if required_from is None or required_from <= today:
            if strength(level) > strength(enforced.level):
                enforced = Requirement(level, required_from, [role])
            elif level == enforced.level:
                enforced.roles.append(role)
    for role, level, required_from in rows:
        if role not in held or required_from is None or required_from <= today:
            continue
        if strength(level) <= strength(enforced.level):
            continue
        if upcoming is None or strength(level) > strength(upcoming.level):
            upcoming = Requirement(level, required_from, [role])
        elif level == upcoming.level:
            upcoming.roles.append(role)
            upcoming.required_from = min(upcoming.required_from, required_from)
    return enforced, upcoming


def status(user, verified, requirement):
    """OK, NEEDS_SETUP or NEEDS_VERIFY: whether an account whose session is
    `verified` (passed two-step login) meets `requirement`."""
    from . import two_step

    if requirement.level == PASSWORD:
        return OK
    has_device = two_step.has_passkey(user) if requirement.level == PASSKEY else two_step.is_on(user)
    if not has_device:
        return NEEDS_SETUP
    return OK if verified else NEEDS_VERIFY


def _is_verified(request):
    is_verified = getattr(request.user, "is_verified", None)
    return bool(is_verified and is_verified())


def request_status(request):
    """status() for this request's account, worked out once per request."""
    if not hasattr(request, "_sign_in_status"):
        user = request.user
        if not user.is_authenticated or user.account_type != User.ADULT:
            request._sign_in_status = OK
        else:
            enforced, _upcoming = requirements_for(user)
            request._sign_in_status = status(user, _is_verified(request), enforced)
    return request._sign_in_status


def meets_requirement(request):
    """Whether this request's account may use what its roles open."""
    return request_status(request) == OK


def meets_requirement_for_session(user, session):
    """meets_requirement() where django_otp's middleware doesn't run (the
    WebSocket consumer): verified means the session holds one of the
    account's own confirmed devices, as OTPMiddleware checks it."""
    from django_otp.models import Device

    if not user.is_authenticated or user.account_type != User.ADULT:
        return True
    device = Device.from_persistent_id(session.get(DEVICE_ID_SESSION_KEY) or "")
    verified = device is not None and device.user_id == user.pk and device.confirmed
    enforced, _upcoming = requirements_for(user)
    return status(user, verified, enforced) == OK


def accounts_with_role(role):
    """Every active adult account holding `role` (the counts on
    /manage/security/); the same rules as roles_of."""
    from django.contrib.auth.models import Permission
    from django.db.models import Q

    from dojos.models import DojoMembership

    accounts = User.objects.filter(account_type=User.ADULT, is_active=True)
    if role == SignInRequirement.SUPERUSER:
        return accounts.filter(is_superuser=True)
    if role == SignInRequirement.ORGANISATION_ADMIN:
        return accounts.filter(organisation_roles__role=OrganisationRole.ADMIN).distinct()
    if role == SignInRequirement.ORGANISATION_BOARD:
        return accounts.filter(organisation_roles__role=OrganisationRole.BOARD).distinct()
    if role == SignInRequirement.REVIEWER:
        permissions = Permission.objects.filter(
            content_type__app_label="applications",
            codename="can_review_background_checks",
        )
        return accounts.filter(
            Q(is_superuser=True) | Q(user_permissions__in=permissions) | Q(groups__permissions__in=permissions)
        ).distinct()
    if role in (SignInRequirement.CHAMPION, SignInRequirement.MENTOR):
        return accounts.filter(
            dojo_memberships__status=DojoMembership.ACTIVE,
            dojo_memberships__role=role,
        ).distinct()
    return accounts


def with_two_step(accounts):
    """The accounts in `accounts` with two-step login on, and with a passkey."""
    from django.db.models import Q

    on = accounts.filter(Q(totpdevice__confirmed=True) | Q(webauthn_keys__confirmed=True)).distinct()
    passkey = accounts.filter(webauthn_keys__confirmed=True).distinct()
    return on, passkey
