"""The yes/no questions a dojo team asks on a session's sign-up
(DATA_MODEL.md §29): a session's own questions and the dojo's default ones
(which a new session starts with), adding, editing, removing and ordering
them, checking and changing the answers, and counting them.

Answers are saved by events.registrations.sign_up, in the same locked
transaction as the registrations; `missing_answers` is the check it runs
after taking the lock."""

from collections.abc import Iterable, Mapping
from typing import TYPE_CHECKING, Any

from django.conf import settings
from django.db import transaction
from django.db.models import Count, Max, Q
from django.utils import timezone
from django.utils.translation import gettext as _

from dojos.models import Dojo, DojoQuestion

from .models import Event, EventQuestion, Registration, RegistrationAnswer

if TYPE_CHECKING:  # types only
    from accounts.models import Ninja

MAX_LENGTH = 200

# {child_id: {question_id: answer}}
Answers = Mapping[int, Mapping[int, bool]]
# A session's own question, or one of its dojo's defaults.
Question = EventQuestion | DojoQuestion
Owner = Event | Dojo


class QuestionError(Exception):
    """A change to a session's (or a dojo's default) questions that can't
    happen, with a message for the dojo team."""


def max_questions() -> int:
    """At most this many questions per session, and as a dojo's defaults
    (settings.SIGNUP_QUESTIONS_MAX, from the environment; 5 by default)."""
    return int(settings.SIGNUP_QUESTIONS_MAX)


def _questions_of(owner: Owner) -> tuple[type[Question], str]:
    """The question model of `owner` and the name of its link to it."""
    if isinstance(owner, Event):
        return EventQuestion, "event"
    return DojoQuestion, "dojo"


def _owner_field(question: Question) -> str:
    return "event" if isinstance(question, EventQuestion) else "dojo"


def _clean_text(text: str) -> str:
    text = (text or "").strip()
    if not text:
        raise QuestionError(_("Write the question."))
    if len(text) > MAX_LENGTH:
        raise QuestionError(_("Keep the question under %(max)s characters.") % {"max": MAX_LENGTH})
    return text


def _check_owner(owner: Owner) -> None:
    if isinstance(owner, Event) and owner.registers_externally:
        raise QuestionError(_("Families sign up for this session on another website, so it has no questions here."))


def add_question(owner: Owner, text: str, translations: Mapping[str, str] | None = None) -> Question:
    """Add a question at the end of the list of `owner`, a session or a
    dojo (its defaults). `translations` is {language: text} for the dojo's
    other languages."""
    _check_owner(owner)
    text = _clean_text(text)
    model, field = _questions_of(owner)
    with transaction.atomic():
        # Locks the session (or dojo), so two team members adding at once
        # can't go past the maximum.
        type(owner).objects.select_for_update().filter(pk=owner.pk).first()
        existing = model.objects.filter(**{field: owner})
        if existing.count() >= max_questions():
            raise QuestionError(_("At most %(max)s questions: remove one first.") % {"max": max_questions()})
        position = (existing.aggregate(Max("position"))["position__max"] or 0) + 1
        question = model(**{field: owner, "text": text, "position": position})
        _set_translations(question, translations)
        question.save()
    return question


def edit_question(question: Question, text: str, translations: Mapping[str, str] | None = None) -> Question:
    """Change a question's wording. Families who already answered saw the
    old wording; a question whose meaning changes is removed and added anew.
    Changing a dojo's default changes only the sessions made after it."""
    question.text = _clean_text(text)
    _set_translations(question, translations)
    question.save(update_fields=["text", "translations"])
    return question


def _set_translations(question: Question, translations: Mapping[str, str] | None) -> None:
    for language in question.content_languages()[1:]:
        if translations is not None and language in translations:
            question.set_translation(language, "text", (translations[language] or "").strip()[:MAX_LENGTH])


def remove_question(question: Question) -> None:
    """Remove a question and (a session's) every answer given to it."""
    question.delete()


def move_question(question: Question, direction: str) -> None:
    """Swap `question` with its neighbour ("up" or "down"). Positions are
    renumbered 1..n on the way, so gaps and ties from the admin don't matter."""
    if direction not in ("up", "down"):
        return
    field = _owner_field(question)
    with transaction.atomic():
        siblings = (
            type(question).objects.select_for_update().filter(**{f"{field}_id": getattr(question, f"{field}_id")})
        )
        questions: list[Any] = list(siblings)
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


def copy_defaults(event: Event) -> list[EventQuestion]:
    """Start a new session with its dojo's default questions (set on the
    dojo's Settings page), so a team that always asks about laptops doesn't
    type it every time; the team changes them per session afterwards.
    Nothing when `event` already has questions or registers on another
    website."""
    if event.registers_externally or event.questions.exists():
        return []
    return EventQuestion.objects.bulk_create(
        EventQuestion(event=event, text=q.text, position=position, translations=q.translations)
        for position, q in enumerate(event.dojo.default_questions.all()[: max_questions()], start=1)
    )


def missing_answers(questions: Iterable[EventQuestion], children: "Iterable[Ninja]", answers: Answers) -> bool:
    """Whether any of `children` lacks an answer to any of `questions`."""
    question_ids = [q.pk for q in questions]
    return any(qid not in (answers.get(child.pk) or {}) for child in children for qid in question_ids)


def save_answers(registration: Registration, questions: Iterable[EventQuestion], answers: Mapping[int, bool]) -> None:
    """The answers for one new registration (called by sign_up, under the lock).
    One save() each, so the audit log records them like the registration."""
    for question in questions:
        RegistrationAnswer.objects.create(
            registration=registration, question=question, answer=bool(answers[question.pk])
        )


def _set_answer(
    registration: Registration, question: EventQuestion, value: bool, existing: RegistrationAnswer | None
) -> bool:
    if existing is None:
        RegistrationAnswer.objects.create(registration=registration, question=question, answer=value)
        return True
    if existing.answer != value:
        existing.answer = value
        existing.answered_at = timezone.now()
        existing.save(update_fields=["answer", "answered_at"])
        return True
    return False


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
            changed |= _set_answer(registration, question, bool(answers[question.pk]), existing.get(question.pk))
        return changed


def correct_answer(registration: Registration, question: EventQuestion, value: bool) -> bool:
    """The dojo team (on the attendance list, or its app through the API)
    sets one child's answer, e.g. at the door: the child did bring a laptop.
    Any time, also once the session has started; the audit log records who
    did it. Returns whether it changed. `question` must be the session's."""
    if question.event_id != registration.event_id:
        raise QuestionError(_("That question isn't one of this session's."))
    existing = RegistrationAnswer.objects.filter(registration=registration, question=question).first()
    return _set_answer(registration, question, bool(value), existing)


def answers_of(registration: Registration) -> list[RegistrationAnswer]:
    """One registration's answers in the session's question order, with the
    question (and its dojo, for its languages) loaded."""
    return list(
        RegistrationAnswer.objects.filter(registration=registration)
        .select_related("question__event__dojo")
        .order_by("question__position", "question_id")
    )


def totals(event: Event) -> list[dict[str, Any]]:
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
