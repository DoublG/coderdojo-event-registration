"""Inviting someone without an account to take organisation roles
(DATA_MODEL.md §23).

An organisation admin enters an address, a name and the roles; the person
gets a link (`organisation_invitation` mail, valid `VALID_DAYS`) and creates
their own account from it, or logs in when they made one since. The roles
are granted only when **an account with that same address** accepts it, so
a forwarded link grants nothing, and "every account is created by its own
holder" still holds. Single use, withdrawable, resendable (a new link:
the old one stops working). The token is stored only as a hash.
Accepted, expired and withdrawn invitations are deleted `KEEP_DAYS` later
by the daily retention job (`remove_old`).

Views only call these functions; `InvitationError` carries a user-facing
message.
"""

import hashlib
import secrets
from collections.abc import Iterable
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from django.conf import settings
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import transaction
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy

from .models import OrganisationInvitation, OrganisationRole, User
from .organisation_people import ROLE_LABELS

if TYPE_CHECKING:
    from django.contrib.auth.models import AnonymousUser

VALID_DAYS = 14
KEEP_DAYS = 30
THROTTLE_SECONDS = 60


class InvitationError(Exception):
    """A user-facing reason the invitation can't be sent or accepted."""


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _new_token(invitation: OrganisationInvitation) -> str:
    token = secrets.token_urlsafe(32)
    invitation.token_hash = _hash(token)
    return token


def find(token: str | None) -> OrganisationInvitation | None:
    """The invitation behind a link's token, or None."""
    if not token:
        return None
    return OrganisationInvitation.objects.filter(token_hash=_hash(token)).first()


def accept_url(token: str) -> str:
    return settings.SITE_URL + reverse("organisation_invitation", kwargs={"token": token})


def _throttle(by: User) -> None:
    if not cache.add(f"organisation-invitation:{by.pk}", True, THROTTLE_SECONDS):
        raise InvitationError(_("You've just sent an invitation: wait a minute before the next one."))


def _mail(invitation: OrganisationInvitation, token: str) -> None:
    from mailing.services import send_to_address

    send_to_address(
        invitation.email,
        "organisation_invitation",
        {
            "invited_by": invitation.invited_by.team_name if invitation.invited_by else "",
            "roles": invitation.roles,
            "accept_url": accept_url(token),
            "valid_days": VALID_DAYS,
        },
        language=invitation.language,
        name=invitation.name,
    )


@transaction.atomic
def invite(
    email: str | None, name: str | None, roles: Iterable[str], by: User, language: str = ""
) -> OrganisationInvitation:
    address = (email or "").strip()
    full_name = (name or "").strip()
    try:
        validate_email(address)
    except ValidationError:
        raise InvitationError(_("Enter a valid email address.")) from None
    wanted = set(roles)
    chosen = [role for role in ROLE_LABELS if role in wanted]
    if not chosen:
        raise InvitationError(_("Choose at least one role."))
    if not full_name:
        raise InvitationError(_("Enter the person's name."))
    if User.objects.filter(email__iexact=address).exists():
        raise InvitationError(_("An account already exists with this email: give it roles from its page instead."))
    if OrganisationInvitation.objects.pending().filter(email__iexact=address).exists():
        raise InvitationError(_("This address already has an invitation waiting: send it again from People."))
    _throttle(by)
    now = timezone.now()
    invitation = OrganisationInvitation(
        email=address,
        name=full_name,
        roles=chosen,
        language=language,
        invited_by=by,
        created_at=now,
        expires_at=now + timedelta(days=VALID_DAYS),
    )
    token = _new_token(invitation)
    invitation.save()
    _mail(invitation, token)
    return invitation


@transaction.atomic
def resend(invitation: OrganisationInvitation, by: User) -> OrganisationInvitation:
    """A new link (the old one stops working), valid VALID_DAYS again."""
    if invitation.accepted_at or invitation.withdrawn_at:
        raise InvitationError(_("This invitation was already accepted or withdrawn."))
    _throttle(by)
    token = _new_token(invitation)
    invitation.expires_at = timezone.now() + timedelta(days=VALID_DAYS)
    invitation.save(update_fields=["token_hash", "expires_at"])
    _mail(invitation, token)
    return invitation


def withdraw(invitation: OrganisationInvitation) -> OrganisationInvitation:
    if not invitation.is_pending:
        raise InvitationError(_("This invitation isn't waiting any more."))
    invitation.withdrawn_at = timezone.now()
    invitation.save(update_fields=["withdrawn_at"])
    return invitation


def can_accept(invitation: OrganisationInvitation, user: "User | AnonymousUser") -> bool:
    return (
        invitation.is_pending
        and user.is_authenticated
        and user.is_active
        and user.account_type == User.ADULT
        and user.email.strip().lower() == invitation.email.strip().lower()
    )


@transaction.atomic
def accept(invitation: OrganisationInvitation, user: User) -> OrganisationInvitation:
    """Grant the invitation's roles to `user`, whose address must be the
    invited one."""
    from notifications.services import notify

    invitation = OrganisationInvitation.objects.select_for_update().get(pk=invitation.pk)
    if not invitation.is_pending:
        raise InvitationError(_("This invitation isn't valid any more."))
    if not can_accept(invitation, user):
        raise InvitationError(_("This invitation is for another email address."))
    held = set(user.organisation_roles.values_list("role", flat=True))
    for role in invitation.roles:
        if role in ROLE_LABELS and role not in held:
            OrganisationRole.objects.create(account=user, role=role)
    invitation.accepted_at = timezone.now()
    invitation.accepted_by = user
    invitation.save(update_fields=["accepted_at", "accepted_by"])
    if invitation.invited_by and invitation.invited_by.is_active:
        notify(
            invitation.invited_by,
            gettext_lazy("%(name)s accepted your invitation to the organisation."),
            url=reverse("manage_person", kwargs={"user_id": user.pk}),
            params={"name": user.team_name},
            organisation=True,
        )
    return invitation


def remove_old(now: datetime | None = None) -> int:
    """The retention job: accepted, withdrawn and expired invitations
    `KEEP_DAYS` after they ended. Returns how many."""
    cutoff = (now or timezone.now()) - timedelta(days=KEEP_DAYS)
    old = (
        OrganisationInvitation.objects.filter(accepted_at__lt=cutoff)
        | OrganisationInvitation.objects.filter(withdrawn_at__lt=cutoff)
        | OrganisationInvitation.objects.filter(expires_at__lt=cutoff)
    )
    return OrganisationInvitation.objects.filter(pk__in=list(old.values_list("pk", flat=True))).delete()[0]
