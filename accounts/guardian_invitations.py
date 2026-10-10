"""A child's guardians: inviting another adult, accepting, withdrawing and
removing (DATA_MODEL_PRIVACY.md §27).

A parent or legal guardian of the child enters an address and the person's
relation to the child (parent, legal guardian or someone else); the person
gets a link (`child_guardian_invitation` mail, valid `VALID_DAYS`) and
creates their own account from it, or logs in. The child is linked only
when **an account with that same address** accepts it, so a forwarded link
grants nothing to an existing account, and "every account is created by its
own holder" still holds. Single use, withdrawable, resendable (a new link:
the old one stops working); the token is stored only as a hash.

Unlike an organisation invitation, **every guardian of the child is told
when an invitation is sent**, not only when it's accepted: in a conflict
between separated parents, the other parent hears of it before it happens
(and can withdraw it). They're told again on accept, and on removal.

`relation` is the legal relationship, never an access level: every guardian
manages the child the same way. It decides only what the law ties to
parental responsibility (`Guardianship.RESPONSIBLE_RELATIONS`): inviting and
removing guardians, the consent to the child's details choosing mail, the
child's GDPR rights (the data export, erasure with the account), and that a
child always keeps at least one parent or legal guardian.

Accepted, expired and withdrawn invitations are deleted `KEEP_DAYS` later by
the daily retention job (`remove_old`). Views only call these functions;
`GuardianInvitationError` carries a user-facing message.
"""

import hashlib
import secrets
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

from .consent import consent_fields
from .models import GuardianInvitation, Guardianship, Ninja, User

if TYPE_CHECKING:
    from django.contrib.auth.models import AnonymousUser

VALID_DAYS = 14
KEEP_DAYS = 30
THROTTLE_SECONDS = 60


class GuardianInvitationError(Exception):
    """A user-facing reason the invitation or removal can't happen."""


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _new_token(invitation: GuardianInvitation) -> str:
    token = secrets.token_urlsafe(32)
    invitation.token_hash = _hash(token)
    return token


def find(token: str | None) -> GuardianInvitation | None:
    """The invitation behind a link's token, or None."""
    if not token:
        return None
    return GuardianInvitation.objects.filter(token_hash=_hash(token)).first()


def accept_url(token: str) -> str:
    return settings.SITE_URL + reverse("guardian_invitation", kwargs={"token": token})


def child_url(child: Ninja) -> str:
    return settings.SITE_URL + reverse("ninja_detail", kwargs={"ninja_id": child.pk})


def responsible_guardianship(child: Ninja, user: User) -> Guardianship | None:
    """`user`'s link to `child` when it holds parental responsibility."""
    return child.guardianships.filter(guardian=user, relation__in=Guardianship.RESPONSIBLE_RELATIONS).first()


def is_responsible(child: Ninja, user: User) -> bool:
    return responsible_guardianship(child, user) is not None


def _require_responsible(child: Ninja, user: User) -> None:
    if not is_responsible(child, user):
        raise GuardianInvitationError(_("Only a parent or legal guardian of the child can do this."))


def _throttle(by: User) -> None:
    if not cache.add(f"guardian-invitation:{by.pk}", True, THROTTLE_SECONDS):
        raise GuardianInvitationError(_("You've just sent an invitation: wait a minute before the next one."))


def _tell_guardians(child: Ninja, template: str, context: dict, *, exclude: User | None = None, key: str) -> None:
    """Mail every guardian of `child` (but `exclude`): service mail, which
    nobody can switch off, since it's about who is responsible for their
    child."""
    from mailing.categories import MailCategory
    from mailing.services import send

    for link in child.guardianships.select_related("guardian"):
        guardian = link.guardian
        if exclude is not None and guardian.pk == exclude.pk:
            continue
        send(
            guardian,
            MailCategory.SERVICE,
            template,
            {"child_name": child.name, "child_url": child_url(child), **context},
            idempotency_key=f"{key}:{guardian.pk}",
        )


def _mail_invitation(invitation: GuardianInvitation, token: str) -> None:
    from mailing.services import send_to_address

    send_to_address(
        invitation.email,
        "child_guardian_invitation",
        {
            "invited_by": invitation.invited_by.team_name if invitation.invited_by else "",
            "child_name": invitation.ninja.name,
            "relation": invitation.relation,
            "accept_url": accept_url(token),
            "valid_days": VALID_DAYS,
        },
        language=invitation.language,
    )


@transaction.atomic
def invite(child: Ninja, email: str | None, relation: str, by: User, language: str = "") -> GuardianInvitation:
    """Invite `email` to become `child`'s guardian as `relation`. `by` must be
    a parent or legal guardian of the child. The other guardians are told."""
    _require_responsible(child, by)
    address = (email or "").strip()
    try:
        validate_email(address)
    except ValidationError:
        raise GuardianInvitationError(_("Enter a valid email address.")) from None
    if relation not in dict(Guardianship.RELATION_CHOICES):
        raise GuardianInvitationError(_("Choose how this person is related to the child."))
    if address.lower() == by.email.strip().lower():
        raise GuardianInvitationError(_("That's your own address."))
    existing = User.objects.filter(email__iexact=address).first()
    if existing is not None and existing.is_ninja:
        raise GuardianInvitationError(_("This address belongs to a child's own login: invite an adult."))
    if existing is not None and child.guardianships.filter(guardian=existing).exists():
        raise GuardianInvitationError(_("This person is already a guardian of %(name)s.") % {"name": child.name})
    if child.guardian_invitations.pending().filter(email__iexact=address).exists():
        raise GuardianInvitationError(_("This address already has an invitation waiting: send it again below."))
    _throttle(by)
    now = timezone.now()
    invitation = GuardianInvitation(
        ninja=child,
        email=address,
        relation=relation,
        # Their own mail language when they have an account; else the
        # inviter's (a family usually shares one).
        language=language or (existing.preferred_language if existing else by.preferred_language),
        invited_by=by,
        created_at=now,
        expires_at=now + timedelta(days=VALID_DAYS),
    )
    token = _new_token(invitation)
    invitation.save()
    _mail_invitation(invitation, token)
    _tell_guardians(
        child,
        "child_guardian_invited",
        {"invited_by": by.team_name, "email": address, "relation": relation, "valid_days": VALID_DAYS},
        exclude=by,
        key=f"guardian-invited:{invitation.pk}",
    )
    return invitation


@transaction.atomic
def resend(invitation: GuardianInvitation, by: User) -> GuardianInvitation:
    """A new link (the old one stops working), valid VALID_DAYS again."""
    _require_responsible(invitation.ninja, by)
    if invitation.accepted_at or invitation.withdrawn_at:
        raise GuardianInvitationError(_("This invitation was already accepted or withdrawn."))
    _throttle(by)
    token = _new_token(invitation)
    invitation.expires_at = timezone.now() + timedelta(days=VALID_DAYS)
    invitation.save(update_fields=["token_hash", "expires_at"])
    _mail_invitation(invitation, token)
    return invitation


def withdraw(invitation: GuardianInvitation, by: User) -> GuardianInvitation:
    """Any parent or legal guardian of the child can withdraw it, not only
    the one who sent it: a co-parent who disagrees can stop it."""
    _require_responsible(invitation.ninja, by)
    if not invitation.is_pending:
        raise GuardianInvitationError(_("This invitation isn't waiting any more."))
    invitation.withdrawn_at = timezone.now()
    invitation.save(update_fields=["withdrawn_at"])
    return invitation


def _still_valid(invitation: GuardianInvitation) -> bool:
    """Pending, and its sender still a parent or legal guardian of the child
    (one who was removed since can't add anyone any more)."""
    return (
        invitation.is_pending
        and invitation.invited_by is not None
        and is_responsible(invitation.ninja, invitation.invited_by)
    )


def can_accept(invitation: GuardianInvitation, user: "User | AnonymousUser") -> bool:
    return (
        _still_valid(invitation)
        and user.is_authenticated
        and user.is_active
        and user.account_type == User.ADULT
        and user.email.strip().lower() == invitation.email.strip().lower()
        and not invitation.ninja.guardianships.filter(guardian=user).exists()
    )


def may_give_consent(invitation: GuardianInvitation) -> bool:
    """Only a parent or legal guardian is asked for the consent to the
    child's details choosing mail (accounts.consent): a trusted adult isn't
    in a position to give it for the child."""
    return invitation.relation in Guardianship.RESPONSIBLE_RELATIONS


@transaction.atomic
def accept(invitation: GuardianInvitation, user: User, consent: bool = False) -> Guardianship:
    """Make `user`, whose address must be the invited one, the child's
    guardian. `consent` counts only for a parent or legal guardian. Every
    other guardian is told."""
    invitation = GuardianInvitation.objects.select_for_update().get(pk=invitation.pk)
    if not _still_valid(invitation):
        raise GuardianInvitationError(_("This invitation isn't valid any more."))
    if not can_accept(invitation, user):
        raise GuardianInvitationError(_("This invitation is for another email address."))
    link = Guardianship.objects.create(
        guardian=user,
        ninja=invitation.ninja,
        relation=invitation.relation,
        **consent_fields(consent and may_give_consent(invitation)),
    )
    invitation.accepted_at = timezone.now()
    invitation.accepted_by = user
    invitation.save(update_fields=["accepted_at", "accepted_by"])
    _tell_guardians(
        invitation.ninja,
        "child_guardian_added",
        {"guardian_name": user.team_name, "relation": invitation.relation},
        exclude=user,
        key=f"guardian-added:{link.pk}",
    )
    return link


def removal_problem(link: Guardianship, by: User) -> str:
    """Why `by` can't remove `link` (empty when they can). Anyone may step
    down from their own link; a parent or legal guardian may remove anyone.
    Either way the child keeps at least one parent or legal guardian."""
    child = link.ninja
    stepping_down = link.guardian_id == by.pk
    if not stepping_down and not is_responsible(child, by):
        return _("Only a parent or legal guardian of the child can remove a guardian.")
    if link.is_responsible:
        others = child.guardianships.exclude(pk=link.pk).filter(relation__in=Guardianship.RESPONSIBLE_RELATIONS)
        if not others.exists():
            if stepping_down:
                return _(
                    "%(name)s always needs a parent or legal guardian on the site, and you're the only one. "
                    "To stop, delete your account (from your account page): %(name)s's details go with it."
                ) % {"name": child.name}
            return _("%(name)s always needs a parent or legal guardian, and this is the only one.") % {
                "name": child.name
            }
    return ""


@transaction.atomic
def remove(link: Guardianship, by: User) -> None:
    """Remove `link` (or step down from it). The removed guardian and the
    remaining ones are mailed, so nobody is cut off without knowing it."""
    link = Guardianship.objects.select_for_update().get(pk=link.pk)
    problem = removal_problem(link, by)
    if problem:
        raise GuardianInvitationError(problem)
    child, removed = link.ninja, link.guardian
    stepped_down = removed.pk == by.pk
    key = f"guardian-removed:{link.pk}:{timezone.now():%Y%m%d%H%M%S}"
    link.delete()
    context = {"guardian_name": removed.team_name, "removed_by": by.team_name, "stepped_down": stepped_down}
    _tell_guardians(child, "child_guardian_removed", {**context, "removed_you": False}, key=key)
    if not stepped_down:
        from mailing.categories import MailCategory
        from mailing.services import send

        send(
            removed,
            MailCategory.SERVICE,
            "child_guardian_removed",
            {"child_name": child.name, "child_url": "", **context, "removed_you": True},
            idempotency_key=f"{key}:{removed.pk}",
        )


def remove_old(now: datetime | None = None) -> int:
    """The retention job: accepted, withdrawn and expired invitations
    `KEEP_DAYS` after they ended. Returns how many."""
    cutoff = (now or timezone.now()) - timedelta(days=KEEP_DAYS)
    old = (
        GuardianInvitation.objects.filter(accepted_at__lt=cutoff)
        | GuardianInvitation.objects.filter(withdrawn_at__lt=cutoff)
        | GuardianInvitation.objects.filter(expires_at__lt=cutoff)
    )
    return GuardianInvitation.objects.filter(pk__in=list(old.values_list("pk", flat=True))).delete()[0]
