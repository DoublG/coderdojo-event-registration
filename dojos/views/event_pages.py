"""A dojo's sessions in its admin area: the events list, creating and editing a
session, its status, its sign-up questions, and the organisation's Promotions card."""

from django.contrib.auth.decorators import login_required
from django.db.models import Count
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from accounts.organisation import Area, has_area
from content.manage import promotion_state
from events import questions as event_questions
from events.forms import EventForm
from events.models import Event, EventQuestion

from ..access import (
    MANAGE_EVENTS,
    require_dojo_access,
)
from ..forms import EventQuestionForm
from .common import _admin_context


@login_required
def dojo_event_list(request, dojo_id):
    access = require_dojo_access(request, dojo_id)
    dojo = access.dojo
    events = dojo.event_set.with_confirmed_count().order_by("-start_time")
    return render(
        request,
        "dojos/dojo_event_list.html",
        {
            "events": events,
            "active": "events",
            **_admin_context(request, access),
        },
    )


@login_required
def dojo_event_create(request, dojo_id):
    """A new session always starts out Draft (Event.status' model default)
    — see EventForm's docstring for why status isn't a field on this form
    at all. The owner publishes it (draft -> open) from the events list
    or its detail page once it's ready, via dojo_event_set_status."""
    access = require_dojo_access(request, dojo_id, MANAGE_EVENTS)
    dojo = access.dojo

    if request.method == "POST":
        form = EventForm(request.POST, request.FILES, instance=Event(dojo=dojo), dojo=dojo)
        if form.is_valid():
            event = form.save()
            # Starts with the questions of the dojo's latest session (removable on its page).
            event_questions.copy_from_latest(event)
            return redirect("dojo_event_list", dojo_id=dojo.id)
    else:
        form = EventForm(instance=Event(dojo=dojo), dojo=dojo)

    return render(
        request,
        "dojos/dojo_event_create.html",
        {
            "form": form,
            "copies_questions": Event.objects.filter(dojo=dojo, questions__isnull=False).exists(),
            "active": "events",
            **_admin_context(request, access),
        },
    )


@login_required
def dojo_event_detail(request, dojo_id, event_id):
    """Edit an existing event — same EventForm as dojo_event_create, just
    bound to an existing instance (EventForm.__init__ pre-fills event_date/
    start_time/end_time from it). Re-renders in place on success, same
    "no redirect, just show a saved banner" convention as dojo_manage,
    since this is an edit-in-place settings-style form, not a one-shot
    creation. Status is changed separately, via dojo_event_set_status —
    the status card at the top of the template posts there directly, so
    saving the form never touches status and vice versa."""
    access = require_dojo_access(request, dojo_id, MANAGE_EVENTS)
    dojo = access.dojo
    event = get_object_or_404(Event, id=event_id, dojo=dojo)
    saved = False

    if request.method == "POST":
        form = EventForm(request.POST, request.FILES, instance=event, dojo=dojo)
        if form.is_valid():
            event = form.save()
            saved = True
    else:
        form = EventForm(instance=event, dojo=dojo)

    return render(
        request,
        "dojos/dojo_event_detail.html",
        {
            "event": event,
            "form": form,
            "saved": saved,
            "active": "events",
            **_questions_context(event),
            **_event_promotions_context(request, event),
            **_admin_context(request, access),
        },
    )


def _questions_context(event, add_form=None, edit_form=None):
    """The event page's Sign-up questions card (DATA_MODEL.md §29): the
    questions with an edit form and how many answered each, the add form
    while there's room, and the totals so far. `add_form`/`edit_form` are a
    posted form to show again with its error."""
    if event.registers_externally:
        return {"questions_shown": False}
    questions = list(event.questions.annotate(answer_count=Count("answers")))
    totals = {row["question"].pk: row for row in event_questions.totals(event)} if questions else {}
    rows = []
    for question in questions:
        form = edit_form if edit_form is not None and edit_form.question.pk == question.pk else None
        rows.append(
            {
                "question": question,
                "form": form or EventQuestionForm(question=question, prefix=f"question-{question.pk}"),
                "open": form is not None,
                "totals": totals.get(question.pk),
            }
        )
    if add_form is None and len(questions) < event_questions.MAX_QUESTIONS:
        add_form = EventQuestionForm(question=EventQuestion(event=event), prefix="new-question")
    return {
        "questions_shown": True,
        "question_rows": rows,
        "question_add_form": add_form,
        "max_questions": event_questions.MAX_QUESTIONS,
    }


def _questions_response(request, access, event, add_form=None, edit_form=None):
    """htmx gets the card back; a plain post (no JavaScript) goes back to the
    event's page, or gets that page with the form's error shown."""
    context = {"dojo": access.dojo, "event": event, **_questions_context(event, add_form, edit_form)}
    if request.headers.get("HX-Request"):
        return render(request, "dojos/partials/_event_questions.html", context)
    if add_form is not None and add_form.errors or edit_form is not None and edit_form.errors:
        return render(
            request,
            "dojos/dojo_event_detail.html",
            {
                **context,
                "form": EventForm(instance=event, dojo=access.dojo),
                "saved": False,
                "active": "events",
                **_event_promotions_context(request, event),
                **_admin_context(request, access),
            },
        )
    return redirect(f"{reverse('dojo_event_detail', args=[access.dojo.id, event.id])}#event-questions")


def _question_event(request, dojo_id, event_id):
    access = require_dojo_access(request, dojo_id, MANAGE_EVENTS)
    event = get_object_or_404(Event, id=event_id, dojo=access.dojo)
    return access, event


@login_required
@require_POST
def dojo_event_question_add(request, dojo_id, event_id):
    """Add a yes/no question to the session's sign-up (events.questions.add_question)."""
    access, event = _question_event(request, dojo_id, event_id)
    form = EventQuestionForm(request.POST, question=EventQuestion(event=event), prefix="new-question")
    if form.is_valid():
        try:
            event_questions.add_question(event, form.cleaned_data["text"], form.translations())
        except event_questions.QuestionError as error:
            form.add_error("text", str(error))
        else:
            form = None
    return _questions_response(request, access, event, add_form=form)


@login_required
@require_POST
def dojo_event_question_edit(request, dojo_id, event_id, question_id):
    """Change a question's wording (events.questions.edit_question)."""
    access, event = _question_event(request, dojo_id, event_id)
    question = get_object_or_404(EventQuestion, id=question_id, event=event)
    form = EventQuestionForm(request.POST, question=question, prefix=f"question-{question.pk}")
    if form.is_valid():
        try:
            event_questions.edit_question(question, form.cleaned_data["text"], form.translations())
        except event_questions.QuestionError as error:
            form.add_error("text", str(error))
        else:
            form = None
    return _questions_response(request, access, event, edit_form=form)


@login_required
@require_POST
def dojo_event_question_remove(request, dojo_id, event_id, question_id):
    """Remove a question and its answers (events.questions.remove_question)."""
    access, event = _question_event(request, dojo_id, event_id)
    event_questions.remove_question(get_object_or_404(EventQuestion, id=question_id, event=event))
    return _questions_response(request, access, event)


@login_required
@require_POST
def dojo_event_question_move(request, dojo_id, event_id, question_id):
    """Move a question up or down (POST `direction`)."""
    access, event = _question_event(request, dojo_id, event_id)
    question = get_object_or_404(EventQuestion, id=question_id, event=event)
    event_questions.move_question(question, request.POST.get("direction", ""))
    return _questions_response(request, access, event)


def _event_promotions_context(request, event):
    """The event page's Promotions card (DATA_MODEL.md §20): only for an
    account with the organisation dashboard's Public site area (§23: the
    admin role), since promoting is the organisation's work (content.manage), the event's promotions with where each stands, and
    whether it can still get one (the promotion form offers events that
    haven't ended)."""
    if not has_area(request.user, Area.PUBLIC_SITE):
        return {"can_promote": False}
    promotions = list(event.promotions.order_by("placement", "rank", "starts_at", "id"))
    visible = set(Event.objects.visible().filter(pk=event.pk).values_list("pk", flat=True))
    now = timezone.now()
    return {
        "can_promote": True,
        "event_promotions": [(p, promotion_state(p, visible, now)) for p in promotions],
        "event_promotable": event.end_time > now,
    }


@login_required
def dojo_event_set_status(request, dojo_id, event_id):
    """Sets an event's status directly — any of draft/open/closed, from any
    other one. Not a one-way lifecycle: an owner can reopen a closed
    session, or pull a published one back to draft (hiding it from the
    public site again — existing registrations are kept, not cancelled).
    Posting an absolute target status (rather than a "next step" action)
    keeps a stale page or double-click harmless: it just re-applies the
    same status. An unknown status value is ignored.

    Redirects back to `next` (posted by whichever page linked here — the
    list or the detail page) when it's a safe same-site URL, else falls
    back to the events list."""
    access = require_dojo_access(request, dojo_id, MANAGE_EVENTS)
    dojo = access.dojo
    event = get_object_or_404(Event, id=event_id, dojo=dojo)

    if request.method == "POST":
        new_status = request.POST.get("status")
        if new_status in dict(Event.STATUS_CHOICES) and new_status != event.status:
            event.status = new_status
            event.save(update_fields=["status"])

    next_url = request.POST.get("next")
    if next_url and url_has_allowed_host_and_scheme(
        next_url, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        return redirect(next_url)
    return redirect("dojo_event_list", dojo_id=dojo.id)
