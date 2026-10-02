"""The account page: the holder's own details (edited in place), changing the
email address (a confirmed flow, accounts.email_change) and cancelling a
child's place."""

from auditlog.context import set_actor
from django.contrib import messages
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import redirect_to_login
from django.db.models import Q
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy

from dojos.team import notify_managers
from events import registrations
from events.models import Registration

from .. import email_change, two_step
from ..forms import (
    AddChildForm,
    ChangeEmailForm,
    EditAccountForm,
)
from ..models import Ninja, User
from .auth import _post_login_redirect


def _children_context(parent):
    now = timezone.now()
    children = []
    for child in Ninja.objects.of_guardian(parent).select_related("account").prefetch_related("belts__belt"):
        # All upcoming registrations, not just the nearest one — a child
        # can be signed up for more than one session at a time. Not
        # filtering on waiting_list either — a waitlisted registration is
        # still "what's coming up" for this child, just flagged as such
        # in the template (see the cd-badge--warning next to it).
        registrations = list(
            child.registration_set.filter(event__start_time__gte=now)
            .select_related("event")
            .order_by("event__start_time")
        )
        children.append({"child": child, "registrations": registrations})
    return children


@login_required
def account_home(request):
    """The logged-in account's own page: their ninjas and what's coming up.
    Any adult account has one (children are optional); a ninja's own login
    is sent to its ninja page instead."""
    if request.user.is_ninja:
        return redirect(_post_login_redirect(request, request.user))
    return _render_account_home(request)


def _render_account_home(request, details_form=None):
    """The account page; with `details_form`, its details are shown as that
    form (edit_account without htmx)."""
    children = _children_context(request.user)
    applications = list(request.user.applications.all())
    active_kinds = {a.kind for a in applications if a.status != "rejected"}
    return render(
        request,
        "accounts/guardian_detail.html",
        {
            "guardian": request.user,
            "form": details_form,
            "children": children,
            "add_child_form": AddChildForm(guardian=request.user),
            "applications": applications,
            "has_champion_application": "champion" in active_kinds,
            "has_mentor_application": "mentor" in active_kinds,
            "two_step_on": two_step.is_on(request.user),
        },
    )


@login_required
def edit_account(request):
    """Click-to-edit for the account page's details (see
    partials/_account_details_display.html), the same shape as edit_ninja:
    GET swaps the details for a small inline form over htmx, POST saves them
    and swaps back. Always the logged-in account's own details; a ninja's
    own login has no account page, so it gets a 404. Without htmx (no
    JavaScript) it shows the whole account page with the form open, and a
    saved form goes back to it."""
    if request.user.is_ninja:
        raise Http404
    is_htmx = request.headers.get("HX-Request") == "true"
    # A copy: validating writes the posted values onto the instance, and an
    # invalid post mustn't change request.user for the rest of the page.
    form = EditAccountForm(request.POST or None, instance=User.objects.get(pk=request.user.pk))
    if request.method == "POST" and form.is_valid():
        account = form.save()
        if not is_htmx:
            messages.success(request, _("Your details are saved."))
            return redirect("account_home")
        return render(request, "accounts/partials/_account_details_display.html", {"guardian": account})
    if not is_htmx:
        return _render_account_home(request, details_form=form)
    return render(request, "accounts/partials/_account_details_edit.html", {"guardian": request.user, "form": form})


@login_required
def change_email(request):
    """The family changes its own email address (DATA_MODEL.md §22): the
    new address and the password; a link goes to the new address, and
    nothing changes until it's opened (confirm_email_change). A ninja's own
    login gets a 404: its address is the guardian's to manage."""
    user = request.user
    if user.is_ninja:
        raise Http404
    form = ChangeEmailForm(user, request.POST if request.method == "POST" else None, request=request)
    if request.method == "POST" and form.is_valid():
        try:
            email_change.request_change(user, form.cleaned_data["new_email"])
        except email_change.EmailChangeError as error:
            form.add_error(None, error.message)
        else:
            messages.success(
                request,
                _(
                    "We sent a link to %(email)s. Open it within %(hours)s hours to confirm; until then your "
                    "address stays %(current)s."
                )
                % {"email": form.cleaned_data["new_email"], "hours": email_change.VALID_HOURS, "current": user.email},
            )
            return redirect("account_home")
    return render(request, "accounts/change_email.html", {"form": form, "valid_hours": email_change.VALID_HOURS})


def confirm_email_change(request, token):
    """The link from the confirmation mail. GET asks, POST changes it (so a
    mail scanner opening the link changes nothing). The family's own link
    needs that account logged in; a link the organisation started works
    logged out too, since the family may not be able to log in any more,
    and then offers a password reset to the new address. Logged in as
    another account: 404."""
    template = "accounts/confirm_email_change.html"
    try:
        change = email_change.read_token(token)
    except email_change.EmailChangeError as error:
        return render(request, template, {"error": error.message}, status=400)
    if request.user.is_authenticated:
        if request.user.pk != change.user.pk:
            raise Http404
    elif change.started_by is None:
        return redirect_to_login(request.get_full_path())

    if request.method != "POST":
        return render(request, template, {"change": change})
    try:
        if request.user.is_authenticated:
            user = email_change.confirm_change(change)
        else:
            # Nobody is logged in: the audit log names the admin who started it.
            with set_actor(change.started_by):
                user = email_change.confirm_change(change)
    except email_change.EmailChangeError as error:
        return render(request, template, {"error": error.message}, status=400)
    if request.user.is_authenticated:
        update_session_auth_hash(request, user)  # the other sessions end, this one stays
        messages.success(request, _("Your email address is now %(email)s.") % {"email": user.email})
        return redirect("account_home")
    return render(request, template, {"done": user})


@login_required
def cancel_registration(request, registration_id):
    registration = get_object_or_404(
        Registration.objects.filter(
            Q(ninja__guardianships__guardian=request.user) | Q(ninja__account=request.user)
        ).distinct(),
        id=registration_id,
    )

    if request.method == "POST":
        event = registration.event
        # A freed confirmed place goes to whoever's been waiting longest for
        # *this* session (Registration.position), under the session's lock
        # (events.registrations).
        if registrations.cancel(registration, cancelled_by=request.user):
            notify_managers(
                event.dojo,
                gettext_lazy("A spot opened up in %(event)s — a waitlisted family is now confirmed."),
                url=reverse("dojo_dashboard", kwargs={"dojo_id": event.dojo_id}),
                params={"event": event.name},
            )

    return redirect("account_home")
