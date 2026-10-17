"""The yes/no sign-up questions in a dojo's admin area (DATA_MODEL.md §29):
the Sign-up questions card on a session's page (the session's own questions,
with the answers so far) and the Default questions card on the dojo's
Settings page (what a new session starts with). One card template and one
set of views for both; the rules are events.questions."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from events import questions as event_questions
from events.models import Event, EventQuestion

from ..access import EDIT_SETTINGS, MANAGE_EVENTS, require_dojo_access
from ..forms import EventQuestionForm
from ..models import DojoQuestion


def questions_context(owner, add_form=None, edit_form=None):
    """The card for `owner`, a session or a dojo (its defaults): each
    question with its edit form and its URLs, the add form while there's
    room, and for a session the answers so far. `add_form`/`edit_form` are
    a posted form to show again with its error."""
    is_event = isinstance(owner, Event)
    if is_event and owner.registers_externally:
        return {"questions_shown": False}
    dojo = owner.dojo if is_event else owner
    if is_event:
        questions = list(owner.questions.annotate(answer_count=Count("answers")))
        totals = {row["question"].pk: row for row in event_questions.totals(owner)} if questions else {}
        kw = {"dojo_id": dojo.id, "event_id": owner.id}
        prefix, new_question = "dojo_event_question", EventQuestion(event=owner)
    else:
        questions = list(owner.default_questions.all())
        totals = {}
        kw = {"dojo_id": dojo.id}
        prefix, new_question = "dojo_default_question", DojoQuestion(dojo=owner)
    rows = []
    for question in questions:
        form = edit_form if edit_form is not None and edit_form.question.pk == question.pk else None
        question_kw = {**kw, "question_id": question.pk}
        rows.append(
            {
                "question": question,
                "form": form or EventQuestionForm(question=question, prefix=f"question-{question.pk}"),
                "open": form is not None,
                "totals": totals.get(question.pk),
                "edit_url": reverse(f"{prefix}_edit", kwargs=question_kw),
                "remove_url": reverse(f"{prefix}_remove", kwargs=question_kw),
                "move_url": reverse(f"{prefix}_move", kwargs=question_kw),
            }
        )
    if add_form is None and len(questions) < event_questions.max_questions():
        add_form = EventQuestionForm(question=new_question, prefix="new-question")
    return {
        "questions_shown": True,
        "questions_for_dojo": not is_event,
        "questions_card_id": "event-questions" if is_event else "default-questions",
        "question_rows": rows,
        "question_add_form": add_form,
        "question_add_url": reverse(f"{prefix}_add", kwargs=kw),
        "max_questions": event_questions.max_questions(),
    }


def _response(request, access, owner, add_form=None, edit_form=None):
    """htmx gets the card back; a plain post (no JavaScript) goes back to the
    page that holds the card, with a form's error as a message."""
    if request.headers.get("HX-Request"):
        return render(
            request,
            "dojos/partials/_questions_card.html",
            {"dojo": access.dojo, **questions_context(owner, add_form, edit_form)},
        )
    for form in (add_form, edit_form):
        if form is not None:
            for error in form.errors.get("text", []):
                messages.error(request, error)
    if isinstance(owner, Event):
        url = reverse("dojo_event_detail", args=[access.dojo.id, owner.id]) + "#event-questions"
    else:
        url = reverse("dojo_manage", args=[access.dojo.id]) + "#default-questions"
    return redirect(url)


def _add(request, access, owner, new_question):
    form = EventQuestionForm(request.POST, question=new_question, prefix="new-question")
    if form.is_valid():
        try:
            event_questions.add_question(owner, form.cleaned_data["text"], form.translations())
        except event_questions.QuestionError as error:
            form.add_error("text", str(error))
        else:
            form = None
    return _response(request, access, owner, add_form=form)


def _edit(request, access, owner, question):
    form = EventQuestionForm(request.POST, question=question, prefix=f"question-{question.pk}")
    if form.is_valid():
        try:
            event_questions.edit_question(question, form.cleaned_data["text"], form.translations())
        except event_questions.QuestionError as error:
            form.add_error("text", str(error))
        else:
            form = None
    return _response(request, access, owner, edit_form=form)


# A session's own questions (MANAGE_EVENTS, scoped to the URL's event).


def _event(request, dojo_id, event_id):
    access = require_dojo_access(request, dojo_id, MANAGE_EVENTS)
    return access, get_object_or_404(Event, id=event_id, dojo=access.dojo)


@login_required
@require_POST
def dojo_event_question_add(request, dojo_id, event_id):
    """Add a yes/no question to the session's sign-up (events.questions.add_question)."""
    access, event = _event(request, dojo_id, event_id)
    return _add(request, access, event, EventQuestion(event=event))


@login_required
@require_POST
def dojo_event_question_edit(request, dojo_id, event_id, question_id):
    """Change a question's wording (events.questions.edit_question)."""
    access, event = _event(request, dojo_id, event_id)
    return _edit(request, access, event, get_object_or_404(EventQuestion, id=question_id, event=event))


@login_required
@require_POST
def dojo_event_question_remove(request, dojo_id, event_id, question_id):
    """Remove a question and its answers (events.questions.remove_question)."""
    access, event = _event(request, dojo_id, event_id)
    event_questions.remove_question(get_object_or_404(EventQuestion, id=question_id, event=event))
    return _response(request, access, event)


@login_required
@require_POST
def dojo_event_question_move(request, dojo_id, event_id, question_id):
    """Move a question up or down (POST `direction`)."""
    access, event = _event(request, dojo_id, event_id)
    question = get_object_or_404(EventQuestion, id=question_id, event=event)
    event_questions.move_question(question, request.POST.get("direction", ""))
    return _response(request, access, event)


# The dojo's default questions (EDIT_SETTINGS, like the Settings page).


@login_required
@require_POST
def dojo_default_question_add(request, dojo_id):
    """Add a default question: new sessions start with it."""
    access = require_dojo_access(request, dojo_id, EDIT_SETTINGS)
    return _add(request, access, access.dojo, DojoQuestion(dojo=access.dojo))


@login_required
@require_POST
def dojo_default_question_edit(request, dojo_id, question_id):
    access = require_dojo_access(request, dojo_id, EDIT_SETTINGS)
    question = get_object_or_404(DojoQuestion, id=question_id, dojo=access.dojo)
    return _edit(request, access, access.dojo, question)


@login_required
@require_POST
def dojo_default_question_remove(request, dojo_id, question_id):
    """Remove a default question; sessions that copied it keep their own."""
    access = require_dojo_access(request, dojo_id, EDIT_SETTINGS)
    event_questions.remove_question(get_object_or_404(DojoQuestion, id=question_id, dojo=access.dojo))
    return _response(request, access, access.dojo)


@login_required
@require_POST
def dojo_default_question_move(request, dojo_id, question_id):
    access = require_dojo_access(request, dojo_id, EDIT_SETTINGS)
    question = get_object_or_404(DojoQuestion, id=question_id, dojo=access.dojo)
    event_questions.move_question(question, request.POST.get("direction", ""))
    return _response(request, access, access.dojo)
