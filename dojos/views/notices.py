"""Telling a session's families about a change (DATA_MODEL_NOTICES.md,
§31): the compose page, reached from the session's page (its Mail the
families card, or the note after a save that changed the venue, times or
places), and the Cancel page, which calls the session off and mails its
families. Whoever can change the session can do both (MANAGE_EVENTS); the
rules are events.notices and events.services.cancel."""

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.translation import gettext as _
from django.utils.translation import ngettext

from events import notices, services
from events.forms import CancelSessionForm, SessionNoticeForm
from events.models import Event, SessionNotice
from mailing.rendering import TemplateMissing

from ..access import MANAGE_EVENTS, require_dojo_access
from .common import _admin_context


def _detail_url(dojo, event, token=""):
    url = reverse("dojo_event_detail", kwargs={"dojo_id": dojo.id, "event_id": event.id})
    return f"{url}?change={token}" if token else url


@login_required
def dojo_event_notify(request, dojo_id, event_id):
    """GET the compose page (`?kind=` picks the kind, `?change=` carries the
    values from before a change); POST with `preview` shows the mail as the
    first family gets it, in the sender's language, without sending; POST
    with `send` sends it and goes back to the session's page."""
    access = require_dojo_access(request, dojo_id, MANAGE_EVENTS)
    dojo = access.dojo
    event = get_object_or_404(Event, id=event_id, dojo=dojo)
    if not notices.can_notify(event):
        messages.error(request, _("There's nobody to mail for this session, or it ended too long ago."))
        return redirect(_detail_url(dojo, event))

    token = request.POST.get("change") or request.GET.get("change") or ""
    before = notices.read_change_token(token, event) if token else None
    if before is None:
        token = ""
    preview = None

    if request.method == "POST":
        form = SessionNoticeForm(request.POST, event=event, before=before)
        if form.is_valid():
            notice = form.build_notice(request.user)
            if "send" in request.POST:
                try:
                    notice = notices.send_notice(notice)
                except notices.NoticeError as error:
                    form.add_error(None, str(error))
                else:
                    messages.success(
                        request,
                        ngettext(
                            "Your mail is on its way to %(count)s family account.",
                            "Your mail is on its way to %(count)s family accounts.",
                            notice.recipients,
                        )
                        % {"count": notice.recipients},
                    )
                    return redirect(_detail_url(dojo, event, token))
            else:
                try:
                    preview = notices.preview(notice, request.user)
                except TemplateMissing:
                    form.add_error(None, _("This mail is missing on the site. Please tell the organisation."))
    else:
        changed = notices.changed_kinds(event, before) if before else []
        kind = request.GET.get("kind")
        if kind not in notices.COMPOSE_KINDS:
            kind = changed[0] if changed else SessionNotice.MESSAGE
        form = SessionNoticeForm(initial={"kind": kind}, event=event, before=before)

    reach = notices.reach(event)
    return render(
        request,
        "dojos/dojo_event_notify.html",
        {
            "event": event,
            "form": form,
            "token": token,
            "preview": preview,
            "audience_reach": [(key, label, reach[key]) for key, label in SessionNotice.AUDIENCE_CHOICES],
            "picked_audience": str(form["audience"].value() or ""),
            "sent_recently": notices.sent_recently(event),
            "limit": settings.SESSION_NOTICES_PER_DAY,
            "active": "events",
            **_admin_context(request, access),
        },
    )


@login_required
def dojo_event_cancel(request, dojo_id, event_id):
    """GET asks (with the families it would mail and an optional note); POST
    cancels the session and, if ticked, mails its families. A session that's
    already cancelled goes back to its page."""
    access = require_dojo_access(request, dojo_id, MANAGE_EVENTS)
    dojo = access.dojo
    event = get_object_or_404(Event, id=event_id, dojo=dojo)
    if event.status == Event.CANCELLED:
        return redirect(_detail_url(dojo, event))

    if request.method == "POST":
        form = CancelSessionForm(request.POST, event=event)
        if form.is_valid():
            try:
                notice = services.cancel(
                    event,
                    cancelled_by=request.user,
                    notify=form.cleaned_data["notify"],
                    message=form.cleaned_data["message"],
                    translations=form.translations(),
                )
            except notices.NoticeError as error:
                form.add_error(None, str(error))
            else:
                if notice:
                    messages.success(
                        request,
                        ngettext(
                            "The session is cancelled, and %(count)s family account is being mailed.",
                            "The session is cancelled, and %(count)s family accounts are being mailed.",
                            notice.recipients,
                        )
                        % {"count": notice.recipients},
                    )
                else:
                    messages.success(request, _("The session is cancelled."))
                return redirect(_detail_url(dojo, event))
    else:
        form = CancelSessionForm(event=event)

    return render(
        request,
        "dojos/dojo_event_cancel.html",
        {
            "event": event,
            "form": form,
            "families": len(notices.recipients(event, SessionNotice.BOTH)),
            "active": "events",
            **_admin_context(request, access),
        },
    )
