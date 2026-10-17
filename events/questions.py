"""The yes/no questions a dojo team asks on a session's sign-up
(DATA_MODEL.md §29): adding, editing, removing and ordering them, copying
them to a new session, checking a sign-up's answers and counting them.

Answers are saved by events.registrations.sign_up, in the same locked
transaction as the registrations; `missing_answers` is the check it runs
after taking the lock."""

from collections.abc import Iterable, Mapping
from typing import TYPE_CHECKING

from django.db import transaction
from django.db.models import Count, Max, Q
from django.utils import timezone
from django.utils.translation import gettext as _

from .models import Event, EventQuestion, Registration, RegistrationAnswer

if TYPE_CHECKING:  # types only
    from accounts.models import Ninja

MAX_QUESTIONS = 5
MAX_LENGTH = 200

# {child_id: {question_id: answer}}
Answers = Mapping[int, Mapping[int, bool]]


class QuestionError(Exception):
    """A change to a session's questions that can't happen, with a message
    for the dojo team."""


def _clean_text(text: str) -> str:
    text = (text or "").strip()
    if not text:
        raise QuestionError(_("Write the question."))
    if len(text) > MAX_LENGTH:
        raise QuestionError(_("Keep the question under %(max)s characters.") % {"max": MAX_LENGTH})
    return text


def _check_event(event: Event) -> None:
    if event.registers_externally:
        raise QuestionError(_("Families sign up for this session on another website, so it has no questions here."))


def add_question(event: Event, text: str, translations: Mapping[str, str] | None = None) -> EventQuestion:
    """Add a question at the end of `event`'s list. `translations` is
    {language: text} for the dojo's other languages."""
    _check_event(event)
    text = _clean_text(text)
    with transaction.atomic():
        # Locks the session, so two team members adding at once can't go past the maximum.
        Event.objects.select_for_update().filter(pk=event.pk).first()
        existing = EventQuestion.objects.filter(event=event)
        if existing.count() >= MAX_QUESTIONS:
            raise QuestionError(
                _("A session can have at most %(max)s questions: remove one first.") % {"max": MAX_QUESTIONS}
            )
        position = (existing.aggregate(Max("position"))["position__max"] or 0) + 1
        question = EventQuestion(event=event, text=text, position=position)
        _set_translations(question, translations)
        question.save()
    return question


def edit_question(question: EventQuestion, text: str, translations: Mapping[str, str] | None = None) -> EventQuestion:
    """Change a question's wording. Families who already answered saw the
    old wording; a question whose meaning changes is removed and added anew."""
    question.text = _clean_text(text)
    _set_translations(question, translations)
    question.save(update_fields=["text", "translations"])
    return question


def _set_translations(question: EventQuestion, translations: Mapping[str, str] | None) -> None:
    for language in question.content_languages()[1:]:
        if translations is not None and language in translations:
            question.set_translation(language, "text", (translations[language] or "").strip()[:MAX_LENGTH])


def remove_question(question: EventQuestion) -> None:
    """Remove a question and every answer given to it."""
    question.delete()


def move_question(question: EventQuestion, direction: str) -> None:
    """Swap `question` with its neighbour ("up" or "down"). Positions are
    renumbered 1..n on the way, so gaps and ties from the admin don't matter."""
    if direction not in ("up", "down"):
        return
    with transaction.atomic():
        questions = list(EventQuestion.objects.select_for_update().filter(event_id=question.event_id))
        index = next((i for i, q in enumerate(questions) if q.pk == question.pk), None)
        if index is None:
            return
        other = index - 1 if direction == "up" else index + 1
        if 0 <= other < len(questions):
            questions[index], questions[other] = questions[other], questions[index]
        for position, item in enumerate(questions, start=1):
            if item.position != position:
                item.position = position
                item.save(update_fields=["position"])


def copy_from_latest(event: Event) -> list[EventQuestion]:
    """Start a new session with the questions of the dojo's most recent
    other session (by start time), so a team that always asks about laptops
    doesn't type it every time. Nothing when `event` already has questions
    or registers on another website."""
    if event.registers_externally or event.questions.exists():
        return []
    latest = (
        Event.objects.filter(dojo_id=event.dojo_id, questions__isnull=False)
        .exclude(pk=event.pk)
        .order_by("-start_time")
        .first()
    )
    if latest is None:
        return []
    return EventQuestion.objects.bulk_create(
        EventQuestion(event=event, text=q.text, position=q.position, translations=q.translations)
        for q in latest.questions.all()[:MAX_QUESTIONS]
    )


def missing_answers(questions: Iterable[EventQuestion], children: "Iterable[Ninja]", answers: Answers) -> bool:
    """Whether any of `children` lacks an answer to any of `questions`."""
    question_ids = [q.pk for q in questions]
    return any(qid not in (answers.get(child.pk) or {}) for child in children for qid in question_ids)


def save_answers(registration: Registration, questions: Iterable[EventQuestion], answers: Mapping[int, bool]) -> None:
    """The answers for one new registration (called by sign_up, under the lock)."""
    RegistrationAnswer.objects.bulk_create(
        RegistrationAnswer(registration=registration, question=q, answer=bool(answers[q.pk])) for q in questions
    )


def change_answers(registration: Registration, answers: Mapping[int, bool]) -> bool:
    """The family changes its answers for one child's place, or answers a
    question added after it signed up (DATA_MODEL.md §29, phase 2): every
    question the session has now, until the session starts. Returns whether
    anything changed. Under the session's lock, like sign_up, so it reads
    the questions as they are."""
    with transaction.atomic():
        event = Event.objects.select_for_update().get(pk=registration.event_id)
        if event.start_time <= timezone.now():
            raise QuestionError(_("This session has started, so the answers can't change any more."))
        questions = list(event.questions.all())
        if any(q.pk not in answers for q in questions):
            raise QuestionError(_("The questions for this session changed, please check them again."))
        existing = {a.question_id: a for a in RegistrationAnswer.objects.filter(registration=registration)}
        changed = False
        for question in questions:
            value = bool(answers[question.pk])
            answer = existing.get(question.pk)
            if answer is None:
                RegistrationAnswer.objects.create(registration=registration, question=question, answer=value)
                changed = True
            elif answer.answer != value:
                answer.answer = value
                answer.answered_at = timezone.now()
                answer.save(update_fields=["answer", "answered_at"])
                changed = True
        return changed


def answers_of(registration: Registration) -> list[RegistrationAnswer]:
    """One registration's answers in the session's question order, with the
    question (and its dojo, for its languages) loaded."""
    return list(
        RegistrationAnswer.objects.filter(registration=registration)
        .select_related("question__event__dojo")
        .order_by("question__position", "question_id")
    )


def totals(event: Event) -> list[dict]:
    """Per question, in order: how many said yes and no, for confirmed
    places and the waiting list separately:
    [{"question", "yes", "no", "waiting_yes", "waiting_no"}]."""
    confirmed = Q(answers__registration__waiting_list=False)
    waiting = Q(answers__registration__waiting_list=True)
    rows = event.questions.annotate(
        yes=Count("answers", filter=confirmed & Q(answers__answer=True)),
        no=Count("answers", filter=confirmed & Q(answers__answer=False)),
        waiting_yes=Count("answers", filter=waiting & Q(answers__answer=True)),
        waiting_no=Count("answers", filter=waiting & Q(answers__answer=False)),
    )
    return [
        {"question": q, "yes": q.yes, "no": q.no, "waiting_yes": q.waiting_yes, "waiting_no": q.waiting_no}
        for q in rows
    ]
