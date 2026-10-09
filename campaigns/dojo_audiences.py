"""The audiences a dojo's team can mail (DATA_MODEL.md §25): a fixed list,
prepared in code, never the organisation's segment builder. Each one turns
(dojo, params) into a segment definition in the resolver's format
(campaigns.segmentation.resolver), which a dojo mailing freezes in
`Campaign.segment_snapshot` at launch like any campaign.

Every audience only reaches families linked to that dojo: a child who goes
there (home dojo, or a recent visit: mailing.dojo_families), or a place at
one of its sessions. The ones that pick children by their details (how they
come to the dojo, their age, a pathway) are `ninja` groups, so the resolver
only picks guardians who gave the child-data consent (accounts.consent).
Gender, belts, badges, cancellations and no-shows are deliberately not
offered (decided). As for every campaign, only adults get the mail.

One audience isn't families: the dojo's own team (its active champion and
mentors), which gets `volunteer` mail in the `dojo_team_message` frame
instead of `dojo_news` in `dojo_message`, and doesn't count towards the
limit on mail to families."""

from dataclasses import dataclass
from datetime import timedelta
from typing import TYPE_CHECKING, Any

from django.db.models import QuerySet
from django.utils import timezone
from django.utils.translation import gettext
from django.utils.translation import gettext_lazy as _

from campaigns.segmentation.resolver import GroupData, RuleData, SegmentDefinition, SegmentResolver
from events.models import Event, NinjaEngagement
from mailing.categories import MailCategory

if TYPE_CHECKING:
    from django_stubs_ext import StrOrPromise

    from dojos.models import Dojo
    from pathways.models import Pathway

FAMILY_TEMPLATE = "dojo_message"
TEAM_TEMPLATE = "dojo_team_message"

RECENT_DAYS = (90, 180, 365)
DEFAULT_RECENT_DAYS = 180
# A mailing about a session can still go out shortly after it ("thanks for coming").
SESSION_DAYS_BACK = 30
MIN_AGE, MAX_AGE = 5, 18


class DojoAudienceError(Exception):
    """A user-facing message: the audience or its parameters don't work."""


@dataclass(frozen=True)
class Audience:
    key: str
    label: "StrOrPromise"
    description: "StrOrPromise"
    params: tuple[str, ...] = ()
    needs_consent: bool = False
    category: str = MailCategory.DOJO_NEWS
    template: str = FAMILY_TEMPLATE

    @property
    def is_team(self) -> bool:
        return self.category == MailCategory.VOLUNTEER


ALL_FAMILIES = "all_families"
SESSION = "session"
WAITING_LIST = "waiting_list"
RECENT = "recent"
NEW_FAMILIES = "new_families"
MISSED = "missed"
AGE = "age"
PATHWAY = "pathway"
TEAM = "team"

AUDIENCES = [
    Audience(
        ALL_FAMILIES,
        _("All families of the dojo"),
        _("Families whose child has the dojo as home dojo, or came to one of its sessions in the last year."),
    ),
    Audience(
        SESSION,
        _("Families booked for a session"),
        _("Families with a place for one of your sessions, and if you like those on its waiting list."),
        params=("event", "include_waiting_list"),
    ),
    Audience(
        WAITING_LIST,
        _("Families on a session's waiting list"),
        _("For example to tell them about an extra session."),
        params=("event",),
    ),
    Audience(
        RECENT,
        _("Families who came recently"),
        _("Families whose child came to one of your sessions in the chosen period."),
        params=("days",),
    ),
    Audience(
        NEW_FAMILIES,
        _("New families"),
        _("Children who only just started coming to your dojo."),
        needs_consent=True,
    ),
    Audience(
        MISSED,
        _("We miss you"),
        _("Children who used to come to your dojo but missed several sessions in a row or stopped coming."),
        needs_consent=True,
    ),
    Audience(
        AGE,
        _("Children of an age"),
        _("Children of your dojo within an age range."),
        params=("min_age", "max_age"),
        needs_consent=True,
    ),
    Audience(
        PATHWAY,
        _("Children on a pathway"),
        _("Children of your dojo who worked on one of your pathways at a session."),
        params=("pathway",),
        needs_consent=True,
    ),
    Audience(
        TEAM,
        _("Your dojo's team"),
        _(
            "The dojo's champion and mentors, for example to plan the next sessions. "
            "It goes out as volunteering mail and doesn't count towards your mails to families."
        ),
        category=MailCategory.VOLUNTEER,
        template=TEAM_TEMPLATE,
    ),
]
BY_KEY = {audience.key: audience for audience in AUDIENCES}


def get(key: str) -> Audience:
    try:
        return BY_KEY[key]
    except KeyError:
        raise DojoAudienceError(gettext("Pick who should get the mail.")) from None


def sessions_for(dojo: "Dojo") -> QuerySet[Event]:
    """The sessions a mailing can be about: published ones, from a month ago on."""
    since = timezone.now() - timedelta(days=SESSION_DAYS_BACK)
    return Event.objects.filter(dojo=dojo, start_time__gte=since).exclude(status=Event.DRAFT).order_by("start_time")


def pathways_for(dojo: "Dojo") -> "QuerySet[Pathway]":
    return dojo.pathways.order_by("name")


def available(dojo: "Dojo") -> list[Audience]:
    """The audiences this dojo can use (the pathway one needs pathways)."""
    has_pathways = pathways_for(dojo).exists()
    return [a for a in AUDIENCES if a.key != PATHWAY or has_pathways]


def _int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def clean_params(key: str, dojo: "Dojo", raw: dict[str, Any] | None) -> dict[str, Any]:
    """The audience's parameters, checked against the dojo: a session or
    pathway of another dojo is refused. Returns a plain dict for
    `Campaign.audience_params`, or raises DojoAudienceError."""
    audience = get(key)
    raw = raw or {}
    params: dict[str, Any] = {}
    if "event" in audience.params:
        event = _int(raw.get("event"))
        if event is None or not sessions_for(dojo).filter(pk=event).exists():
            raise DojoAudienceError(gettext("Pick one of your dojo's sessions."))
        params["event"] = event
    if "include_waiting_list" in audience.params:
        params["include_waiting_list"] = bool(raw.get("include_waiting_list"))
    if "days" in audience.params:
        days = _int(raw.get("days"))
        if days not in RECENT_DAYS:
            raise DojoAudienceError(gettext("Pick a period."))
        params["days"] = days
    if "min_age" in audience.params:
        low, high = _int(raw.get("min_age")), _int(raw.get("max_age"))
        if low is None or high is None or not MIN_AGE <= low <= high <= MAX_AGE:
            raise DojoAudienceError(
                gettext("Give an age range between %(min)s and %(max)s, the youngest age first.")
                % {"min": MIN_AGE, "max": MAX_AGE}
            )
        params["min_age"], params["max_age"] = low, high
    if "pathway" in audience.params:
        pathway = _int(raw.get("pathway"))
        if pathway is None or not pathways_for(dojo).filter(pk=pathway).exists():
            raise DojoAudienceError(gettext("Pick one of your dojo's pathways."))
        params["pathway"] = pathway
    return params


def _group(scope: str, rules: list[RuleData], operator: str = "and") -> GroupData:
    return {"scope": scope, "operator": operator, "rules": rules, "children": []}


def _rule(attribute: str, operator: str, value: Any) -> RuleData:
    return {"attribute": attribute, "operator": operator, "value": value}


def definition(key: str, dojo: "Dojo", params: dict[str, Any] | None) -> SegmentDefinition:
    """The segment definition for the audience, limited to `dojo`. Checks
    the parameters first (clean_params)."""
    params = clean_params(key, dojo, params)
    child_of_dojo = _rule("ninja_of_dojo", "equals", dojo.pk)
    if key == ALL_FAMILIES:
        groups = [_group("user", [_rule("dojo_family", "equals", dojo.pk)])]
    elif key == TEAM:
        groups = [_group("user", [_rule("dojo_team", "equals", dojo.pk)])]
    elif key == SESSION:
        rules = [_rule("family_booked_for_event", "equals", params["event"])]
        if params["include_waiting_list"]:
            rules.append(_rule("family_waitlisted_for_event", "equals", params["event"]))
        groups = [_group("user", rules, "or")]
    elif key == WAITING_LIST:
        groups = [_group("user", [_rule("family_waitlisted_for_event", "equals", params["event"])])]
    elif key == RECENT:
        value = {"dojo": dojo.pk, "days": params["days"]}
        groups = [_group("user", [_rule("family_visited_dojo", "within_days", value)])]
    elif key == NEW_FAMILIES:
        value = {"dojo": dojo.pk, "stages": [NinjaEngagement.NEW]}
        groups = [_group("ninja", [_rule("engagement_stage_at_dojo", "in", value)])]
    elif key == MISSED:
        value = {"dojo": dojo.pk, "stages": [NinjaEngagement.AT_RISK, NinjaEngagement.LAPSED]}
        groups = [_group("ninja", [_rule("engagement_stage_at_dojo", "in", value)])]
    elif key == AGE:
        groups = [
            _group(
                "ninja",
                [
                    child_of_dojo,
                    _rule("ninja_age", "gte", params["min_age"]),
                    _rule("ninja_age", "lte", params["max_age"]),
                ],
            )
        ]
    else:  # PATHWAY
        groups = [_group("ninja", [child_of_dojo, _rule("pathway", "equals", params["pathway"])])]
    return {"name": str(get(key).label), "groups": groups}


def describe(key: str, dojo: "Dojo", params: dict[str, Any] | None) -> str:
    """The audience as one sentence, for the dojo's pages."""
    audience = BY_KEY.get(key)
    if audience is None:
        return ""
    params = params or {}
    if key in (SESSION, WAITING_LIST):
        event = Event.objects.filter(pk=params.get("event"), dojo=dojo).first()
        name = event.localized("name") if event else gettext("a session")
        when = timezone.localtime(event.start_time).strftime("%d/%m/%Y") if event else ""
        if key == WAITING_LIST:
            return gettext("Families on the waiting list for %(session)s (%(date)s)") % {"session": name, "date": when}
        if params.get("include_waiting_list"):
            return gettext("Families booked for %(session)s (%(date)s), waiting list included") % {
                "session": name,
                "date": when,
            }
        return gettext("Families booked for %(session)s (%(date)s)") % {"session": name, "date": when}
    if key == RECENT:
        return gettext("Families whose child came in the last %(days)s days") % {"days": params.get("days")}
    if key == AGE:
        return gettext("Children aged %(min)s to %(max)s") % {
            "min": params.get("min_age"),
            "max": params.get("max_age"),
        }
    if key == PATHWAY:
        pathway_id = params.get("pathway")
        pathway = pathways_for(dojo).filter(pk=pathway_id).first() if pathway_id is not None else None
        return gettext("Children on the pathway %(pathway)s") % {
            "pathway": pathway.localized("name") if pathway else "?"
        }
    return str(audience.label)


def reach(key: str, dojo: "Dojo", params: dict[str, Any] | None) -> tuple[int, int]:
    """(accounts it reaches, families it leaves out for lack of the
    child-data consent): only accounts who want this kind of mail from the
    dojo count."""
    from campaigns.services import wanting

    audience = get(key)
    snapshot = definition(key, dojo, params)
    reached = wanting(SegmentResolver().resolve_definition(snapshot), dojo, audience.category)
    if not audience.needs_consent:
        return reached.count(), 0
    everyone = wanting(SegmentResolver(require_consent=False).resolve_definition(snapshot), dojo, audience.category)
    return reached.count(), everyone.exclude(pk__in=reached.values("pk")).count()
