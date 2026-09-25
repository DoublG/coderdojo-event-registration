import re
import smtplib
from datetime import timedelta
from io import StringIO
from unittest.mock import patch

from django.contrib.gis.geos import MultiPolygon, Point, Polygon
from django.core import mail as django_mail
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.db import transaction
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import Guardianship, Ninja, User
from dojos.models import Dojo, DojoMembership
from dojos.testing import add_member, make_dojo
from events.models import Event, Registration
from geo.models import AdministrativeBoundary, Municipality

from . import campaigns, journeys
from .categories import MailCategory
from .models import (
    BounceRecord,
    Campaign,
    ConsentEvent,
    EmailMessage,
    EmailSuppression,
    EmailTemplate,
    MailPreference,
    ProcessedImapMessage,
    Segment,
    SegmentGroup,
    SegmentRule,
)
from .preferences import is_subscribed, preferences_for, set_preference, subscribed_q
from .rendering import TemplateMissing, render
from .seed_templates import SAMPLE_CONTEXT, TEMPLATES
from .segmentation.registry import get_attributes
from .segmentation.resolver import SegmentResolver
from .services import send, unsubscribe_token
from .tasks import (
    SendBatchTask,
    TransientSendError,
    _claim_pending,
    requeue_stuck_emails,
    send_email_batch,
    send_pending_emails,
)
from .testing import complaint_report, dsn_report


def _family(username, *genders, **fields):
    """An adult account with one child per gender given."""
    fields.setdefault("email", f"{username}@example.com")
    guardian = User.objects.create(username=username, **fields)
    for index, gender in enumerate(genders):
        ninja = Ninja.objects.create(name=f"{username}-kid-{index}", gender=gender)
        Guardianship.objects.create(guardian=guardian, ninja=ninja)
    return guardian


def _segment(*groups):
    """groups: (scope, operator, [(attribute, operator, value), ...])"""
    segment = Segment.objects.create(name="Test")
    for scope, operator, rules in groups:
        group = SegmentGroup.objects.create(segment=segment, scope=scope, operator=operator)
        for attribute, rule_operator, value in rules:
            SegmentRule.objects.create(group=group, attribute=attribute, operator=rule_operator, value=value)
    return segment


def _resolve(segment):
    return set(SegmentResolver().resolve(segment).values_list("username", flat=True))


class SegmentResolverTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        _family("girl", Ninja.GIRL)
        _family("unlisted", Ninja.UNSPECIFIED)
        _family("boy", Ninja.BOY)
        _family("other", Ninja.OTHER)
        _family("mixed", Ninja.BOY, Ninja.GIRL)
        _family("inactive", Ninja.GIRL, is_active=False)
        _family("no-email", Ninja.GIRL)
        User.objects.filter(username="no-email").update(email="")
        User.objects.create(username="volunteer", email="volunteer@example.com")
        User.objects.create(username="teen", email="teen@example.com", account_type=User.NINJA)

    def test_girlz_segment_selects_families_with_a_girl_or_an_unlisted_child(self):
        segment = _segment(("ninja", "and", [("ninja_gender", "in", [Ninja.GIRL, Ninja.UNSPECIFIED])]))
        self.assertEqual(_resolve(segment), {"girl", "unlisted", "mixed"})

    def test_everyone_active_selects_every_active_adult_with_an_email(self):
        segment = _segment(("user", "and", [("account_type", "equals", User.ADULT)]))
        self.assertEqual(_resolve(segment), {"girl", "unlisted", "boy", "other", "mixed", "volunteer"})

    def test_ninja_accounts_never_receive_campaigns(self):
        segment = _segment(("user", "and", [("account_type", "equals", User.NINJA)]))
        self.assertEqual(_resolve(segment), set())

    def test_segment_without_rules_resolves_to_nobody(self):
        segment = Segment.objects.create(name="Empty")
        SegmentGroup.objects.create(segment=segment, scope="user")
        self.assertEqual(_resolve(segment), set())

    def test_rules_in_a_ninja_group_describe_the_same_child(self):
        """"A girl registered for the event" must not match a family whose
        boy is registered and whose girl isn't."""
        event = Event.objects.create(
            name="Girlz", dojo=make_dojo(), status=Event.OPEN, places=10,
            start_time=timezone.now() + timedelta(days=3), end_time=timezone.now() + timedelta(days=3, hours=2),
        )
        mixed_boy = Ninja.objects.get(name="mixed-kid-0")
        Registration.objects.create(event=event, ninja=mixed_boy, waiting_list=False, position=1)
        Registration.objects.create(event=event, ninja=Ninja.objects.get(name="girl-kid-0"), waiting_list=False, position=2)

        segment = _segment(("ninja", "and", [
            ("ninja_gender", "equals", Ninja.GIRL),
            ("event", "equals", event.pk),
        ]))
        self.assertEqual(_resolve(segment), {"girl"})

    def test_two_rules_on_the_same_relation_are_independent_subqueries(self):
        """Registered for event A *and* event B: two different
        registrations, which a single join would never match."""
        dojo = make_dojo()
        start = timezone.now() + timedelta(days=3)
        a, b = (
            Event.objects.create(name=n, dojo=dojo, status=Event.OPEN, places=5, start_time=start,
                                 end_time=start + timedelta(hours=2))
            for n in "AB"
        )
        kid = Ninja.objects.get(name="girl-kid-0")
        Registration.objects.create(event=a, ninja=kid, waiting_list=False, position=1)
        Registration.objects.create(event=b, ninja=kid, waiting_list=False, position=1)

        segment = _segment(("ninja", "and", [("event", "equals", a.pk), ("event", "equals", b.pk)]))
        self.assertEqual(_resolve(segment), {"girl"})

    def test_root_groups_are_anded(self):
        segment = _segment(
            ("ninja", "and", [("ninja_gender", "equals", Ninja.GIRL)]),
            ("user", "and", [("language", "in", ["", "en-us"])]),
        )
        User.objects.filter(username="mixed").update(preferred_language="nl-be")
        self.assertEqual(_resolve(segment), {"girl"})

    def test_has_children(self):
        segment = _segment(("user", "and", [("has_children", "is", True)]))
        self.assertEqual(_resolve(segment), {"girl", "unlisted", "boy", "other", "mixed"})
        segment = _segment(("user", "and", [("has_children", "is", False)]))
        self.assertEqual(_resolve(segment), {"volunteer"})

    def test_or_group(self):
        segment = _segment(("ninja", "or", [
            ("ninja_gender", "equals", Ninja.BOY),
            ("ninja_gender", "equals", Ninja.OTHER),
        ]))
        self.assertEqual(_resolve(segment), {"boy", "other", "mixed"})


def _session(dojo, days_ago, status=Event.CLOSED):
    start = timezone.now() - timedelta(days=days_ago)
    return Event.objects.create(name=f"Session {days_ago}", dojo=dojo, status=status, places=20,
                                start_time=start, end_time=start + timedelta(hours=2))


class ActivityAttributeTests(TestCase):
    """"Everyone active": volunteers whose dojo held a session in the last N
    days, and families whose child came to one, with the same N."""

    def _team_members(self, days):
        return _resolve(_segment(("user", "and", [("active_team_member", "within_days", days)])))

    def _families(self, days):
        return _resolve(_segment(("ninja", "and", [("attended_within_days", "within_days", days)])))

    def test_champions_and_mentors_of_an_active_dojo_with_recent_sessions(self):
        busy, quiet = make_dojo("Busy"), make_dojo("Quiet")
        dormant = make_dojo("Dormant", status=Dojo.DORMANT)
        _session(busy, days_ago=30)
        _session(quiet, days_ago=400)
        _session(dormant, days_ago=30)
        _session(quiet, days_ago=-10, status=Event.OPEN)  # upcoming: not held yet
        for name, dojo, role, status in [
            ("champion", busy, DojoMembership.CHAMPION, DojoMembership.ACTIVE),
            ("mentor", busy, DojoMembership.MENTOR, DojoMembership.ACTIVE),
            ("left", busy, DojoMembership.MENTOR, DojoMembership.DORMANT),
            ("requested", busy, DojoMembership.MENTOR, DojoMembership.REQUESTED),
            ("quiet-mentor", quiet, DojoMembership.MENTOR, DojoMembership.ACTIVE),
            ("dormant-champion", dormant, DojoMembership.CHAMPION, DojoMembership.ACTIVE),
        ]:
            add_member(dojo, User.objects.create(username=name, email=f"{name}@example.com"), role, status=status)

        self.assertEqual(self._team_members(365), {"champion", "mentor"})
        self.assertEqual(self._team_members(500), {"champion", "mentor", "quiet-mentor"})

    def test_draft_sessions_dont_count(self):
        dojo = make_dojo()
        _session(dojo, days_ago=30, status=Event.DRAFT)
        add_member(dojo, User.objects.create(username="champion", email="c@example.com"), DojoMembership.CHAMPION)
        self.assertEqual(self._team_members(365), set())

    def test_families_whose_child_came_recently(self):
        dojo = make_dojo()
        recent, old = _session(dojo, days_ago=20), _session(dojo, days_ago=400)
        kids = {name: Ninja.objects.of_guardian(_family(name, Ninja.GIRL)).get()
                for name in ["came", "absent", "long-ago", "waitlisted"]}
        Registration.objects.create(event=recent, ninja=kids["came"], waiting_list=False, position=1, attended=True)
        Registration.objects.create(event=recent, ninja=kids["absent"], waiting_list=False, position=2, attended=False)
        Registration.objects.create(event=recent, ninja=kids["waitlisted"], waiting_list=True, position=3)
        Registration.objects.create(event=old, ninja=kids["long-ago"], waiting_list=False, position=1, attended=True)

        self.assertEqual(self._families(365), {"came"})
        self.assertEqual(self._families(500), {"came", "long-ago"})

    def test_unmarked_session_counts_confirmed_places(self):
        """A dojo that marked nobody at a session: a confirmed place counts
        as having come, a waitlisted one doesn't."""
        unmarked = _session(make_dojo(), days_ago=20)
        confirmed = Ninja.objects.of_guardian(_family("confirmed", Ninja.BOY)).get()
        waitlisted = Ninja.objects.of_guardian(_family("waitlisted", Ninja.BOY)).get()
        Registration.objects.create(event=unmarked, ninja=confirmed, waiting_list=False, position=1)
        Registration.objects.create(event=unmarked, ninja=waitlisted, waiting_list=True, position=2)

        self.assertEqual(self._families(365), {"confirmed"})

    def test_days_must_be_a_positive_whole_number(self):
        group = SegmentGroup.objects.create(segment=Segment.objects.create(name="x"), scope="user")
        for value in [0, -5, "365", 1.5, True]:
            with self.subTest(value=value), self.assertRaises(ValidationError):
                SegmentRule(group=group, attribute="active_team_member", operator="within_days", value=value).full_clean()


class LocalityAttributeTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        square = MultiPolygon(Polygon(((3.0, 50.5), (4.5, 50.5), (4.5, 51.5), (3.0, 51.5), (3.0, 50.5))), srid=4326)
        cls.east_flanders = AdministrativeBoundary.objects.create(
            kind=AdministrativeBoundary.PROVINCE, name="Provincie Oost-Vlaanderen", boundary=square,
        )
        Municipality.objects.create(postal_code="9000", name="Gent", center=Point(3.7174, 51.0543, srid=4326))
        Municipality.objects.create(postal_code="1000", name="Bruxelles", center=Point(4.3517, 50.8503, srid=4326))
        # Brussels sits inside the test square: move it out, as in the real
        # boundary data (Brussels-Capital isn't a province).
        Municipality.objects.filter(postal_code="1000").update(center=Point(4.8, 50.85, srid=4326))
        Municipality.objects.create(postal_code="3500", name="Hasselt", center=Point(5.3378, 50.9307, srid=4326))
        cls.ghent_dojo = make_dojo("Ghent", location=Point(3.72, 51.05, srid=4326))
        User.objects.create(username="ghent", email="g@example.com", postal_code="9000")
        User.objects.create(username="brussels", email="b@example.com", postal_code="1000")
        User.objects.create(username="hasselt", email="h@example.com", postal_code="3500")
        User.objects.create(username="unknown", email="u@example.com")

    def test_province(self):
        segment = _segment(("user", "and", [("province", "equals", self.east_flanders.pk)]))
        self.assertEqual(_resolve(segment), {"ghent"})

    def test_brussels_capital_region(self):
        segment = _segment(("user", "and", [("province", "in", ["brussels"])]))
        self.assertEqual(_resolve(segment), {"brussels"})

    def test_near_dojo(self):
        segment = _segment(("user", "and", [("near_dojo", "within", {"dojo": self.ghent_dojo.pk, "km": 25})]))
        self.assertEqual(_resolve(segment), {"ghent"})
        wide = _segment(("user", "and", [("near_dojo", "within", {"dojo": self.ghent_dojo.pk, "km": 150})]))
        self.assertEqual(_resolve(wide), {"ghent", "brussels", "hasselt"})

    def test_language(self):
        User.objects.filter(username="hasselt").update(preferred_language="nl-be")
        segment = _segment(("user", "and", [("language", "equals", "nl-be")]))
        self.assertEqual(_resolve(segment), {"hasselt"})


class SegmentRuleValidationTests(TestCase):
    def setUp(self):
        segment = Segment.objects.create(name="Test")
        self.user_group = SegmentGroup.objects.create(segment=segment, scope="user")
        self.ninja_group = SegmentGroup.objects.create(segment=segment, scope="ninja")

    def _clean(self, group, attribute, operator, value):
        SegmentRule(group=group, attribute=attribute, operator=operator, value=value).full_clean()

    def test_valid_rule_passes(self):
        self._clean(self.ninja_group, "ninja_gender", "in", [Ninja.GIRL, Ninja.UNSPECIFIED])

    def test_unknown_attribute(self):
        with self.assertRaises(ValidationError):
            self._clean(self.user_group, "shoe_size", "equals", 42)

    def test_wrong_scope(self):
        with self.assertRaises(ValidationError):
            self._clean(self.user_group, "ninja_gender", "equals", Ninja.GIRL)

    def test_unsupported_operator(self):
        with self.assertRaises(ValidationError):
            self._clean(self.ninja_group, "ninja_gender", "within", Ninja.GIRL)

    def test_unknown_value(self):
        with self.assertRaises(ValidationError):
            self._clean(self.ninja_group, "ninja_gender", "equals", "dragon")

    def test_list_operator_needs_a_list(self):
        with self.assertRaises(ValidationError):
            self._clean(self.ninja_group, "ninja_gender", "in", Ninja.GIRL)

    def test_near_dojo_needs_dojo_and_km(self):
        with self.assertRaises(ValidationError):
            self._clean(self.user_group, "near_dojo", "within", {"km": 10})

    def test_child_group_cannot_contain_account_group(self):
        group = SegmentGroup(segment=self.ninja_group.segment, parent=self.ninja_group, scope="user")
        with self.assertRaises(ValidationError):
            group.full_clean()

    def test_every_registered_attribute_can_be_instantiated(self):
        self.assertTrue(all(attribute.key and attribute.operators for attribute in get_attributes()))


class RenderingTests(TestCase):
    def setUp(self):
        EmailTemplate.objects.create(key="hello", language="en-us", category="service",
                                     subject="Hi {{ name }}", body="Hello {{ name }} & <you>")
        EmailTemplate.objects.create(key="hello", language="nl-be", category="service",
                                     subject="Dag {{ name }}", body="Hallo {{ name }}")

    def test_renders_in_the_requested_language(self):
        self.assertEqual(render("hello", "nl-be", {"name": "An"}), ("Dag An", "Hallo An\n"))

    def test_falls_back_to_english(self):
        self.assertEqual(render("hello", "fr-be", {"name": "An"})[0], "Hi An")

    def test_plain_text_is_not_html_escaped(self):
        self.assertEqual(render("hello", "en-us", {"name": "A&B"})[1], "Hello A&B & <you>\n")

    def test_missing_template(self):
        with self.assertRaises(TemplateMissing):
            render("nope", "en-us", {})


class SeedMailingTests(TestCase):
    def test_seeds_templates_and_campaigns_and_is_rerun_safe(self):
        call_command("seed_mailing", stdout=StringIO())
        EmailTemplate.objects.filter(key="campaign_girlz", language="en-us").update(subject="Edited")
        call_command("seed_mailing", stdout=StringIO())

        self.assertEqual(EmailTemplate.objects.count(), len(TEMPLATES) * 3)
        self.assertEqual(EmailTemplate.objects.get(key="campaign_girlz", language="en-us").subject, "Edited")
        # No dojo with a location in this test database: the new-dojo
        # campaign is skipped rather than seeded half-configured.
        self.assertEqual(set(Campaign.objects.values_list("name", flat=True)), {"Coolest Projects", "CoderDojo Girlz"})
        self.assertEqual(SegmentRule.objects.count(), 3)  # everyone active: 2, Girlz: 1
        self.assertTrue(all(c.status == Campaign.Status.DRAFT for c in Campaign.objects.all()))

    def test_every_seeded_template_renders_in_every_language(self):
        call_command("seed_mailing", stdout=StringIO())
        for template in EmailTemplate.objects.all():
            with self.subTest(template=str(template)):
                subject, body = render(template.key, template.language, SAMPLE_CONTEXT[template.key])
                self.assertNotIn("{{", subject + body)
                self.assertNotIn("{%", body)
                self.assertTrue(subject.strip())

    def test_new_dojo_campaign_targets_families_near_a_draft_dojo(self):
        Municipality.objects.create(postal_code="9880", name="Aalter", center=Point(3.4478, 51.0859, srid=4326))
        Municipality.objects.create(postal_code="3500", name="Hasselt", center=Point(5.3378, 50.9307, srid=4326))
        make_dojo("Older dojo", location=Point(5.3378, 50.9307, srid=4326))
        new = make_dojo("Aalter", status=Dojo.DRAFT, location=Point(3.45, 51.08, srid=4326))
        _family("near", Ninja.BOY, postal_code="9880")
        _family("far", Ninja.GIRL, postal_code="3500")
        User.objects.create(username="mentor-nearby", email="m@example.com", postal_code="9880")

        call_command("seed_mailing", stdout=StringIO())

        campaign = Campaign.objects.get(name="New dojo opening")
        self.assertEqual(campaign.context, {"dojo_name": "Aalter", "dojo_path": f"/dojos/{new.pk}/"})
        self.assertEqual(_resolve(campaign.segment), {"near"})

    def test_seeded_campaign_segments_resolve(self):
        dojo = make_dojo()
        session = _session(dojo, days_ago=30)
        girl_family = _family("girl", Ninja.GIRL)
        _family("boy", Ninja.BOY)
        Registration.objects.create(event=session, ninja=Ninja.objects.of_guardian(girl_family).get(),
                                    waiting_list=False, position=1, attended=True)
        champion = User.objects.create(username="champion", email="c@example.com")
        add_member(dojo, champion, DojoMembership.CHAMPION)

        call_command("seed_mailing", stdout=StringIO())

        resolve = {c.name: _resolve(c.segment) for c in Campaign.objects.select_related("segment")}
        # Dojo has no location, so no new-dojo campaign here.
        self.assertEqual(resolve, {"Coolest Projects": {"girl", "champion"}, "CoderDojo Girlz": {"girl"}})


# --- phase 3: preferences, the send() gateway, the queue ---------------------

Status = EmailMessage.Status


def _templates():
    for language, greeting in [("en-us", "Hello"), ("nl-be", "Hallo")]:
        EmailTemplate.objects.create(key="note", language=language, category=MailCategory.REMINDER,
                                     subject=f"{greeting} {{{{ recipient_name }}}}",
                                     body=f"{greeting}! {{{{ extra }}}} {{{{ unsubscribe_url }}}}")
    EmailTemplate.objects.create(key="account", language="en-us", category=MailCategory.SERVICE,
                                 subject="Your account", body="Account mail. {{ unsubscribe_url }}")


class PreferenceTests(TestCase):
    def setUp(self):
        self.parent = User.objects.create(username="parent", email="p@example.com")
        self.teen = User.objects.create(username="teen", email="t@example.com", account_type=User.NINJA)

    def test_defaults(self):
        self.assertTrue(is_subscribed(self.parent, MailCategory.REMINDER))
        self.assertTrue(is_subscribed(self.parent, MailCategory.DOJO_NEWS))
        self.assertFalse(is_subscribed(self.parent, MailCategory.NEWSLETTER))
        self.assertTrue(is_subscribed(self.parent, MailCategory.SERVICE))

    def test_ninja_accounts_only_get_their_own_kinds_of_mail(self):
        self.assertEqual(set(preferences_for(self.teen)),
                         {MailCategory.SERVICE, MailCategory.REGISTRATION, MailCategory.REMINDER, MailCategory.DOJO_NEWS})
        self.assertFalse(is_subscribed(self.teen, MailCategory.NEWSLETTER))
        self.assertFalse(set_preference(self.teen, MailCategory.NEWSLETTER, True, ConsentEvent.PREFERENCES))
        self.assertFalse(is_subscribed(self.teen, MailCategory.NEWSLETTER))

    def test_changes_are_logged_once(self):
        self.assertTrue(set_preference(self.parent, MailCategory.NEWSLETTER, True, ConsentEvent.SIGNUP))
        self.assertFalse(set_preference(self.parent, MailCategory.NEWSLETTER, True, ConsentEvent.PREFERENCES))
        self.assertTrue(set_preference(self.parent, MailCategory.NEWSLETTER, False, ConsentEvent.UNSUBSCRIBE_LINK))
        log = list(ConsentEvent.objects.order_by("id").values_list("subscribed", "source", "wording_version"))
        self.assertEqual(log, [(True, "signup", "2026-09-25"), (False, "unsubscribe_link", "2026-09-25")])

    def test_mail_that_cant_be_switched_off(self):
        self.assertFalse(set_preference(self.parent, MailCategory.SERVICE, False, ConsentEvent.PREFERENCES))
        self.assertTrue(is_subscribed(self.parent, MailCategory.SERVICE))
        self.assertFalse(MailPreference.objects.exists())

    def test_subscribed_q_matches_is_subscribed(self):
        other = User.objects.create(username="other", email="o@example.com")
        set_preference(self.parent, MailCategory.NEWSLETTER, True, ConsentEvent.SIGNUP)
        set_preference(other, MailCategory.REMINDER, False, ConsentEvent.PREFERENCES)
        for category in [MailCategory.NEWSLETTER, MailCategory.REMINDER, MailCategory.SERVICE]:
            with self.subTest(category=category):
                in_db = set(User.objects.filter(pk__in=[self.parent.pk, other.pk]).filter(subscribed_q(category))
                            .values_list("username", flat=True))
                in_python = {u.username for u in (self.parent, other) if is_subscribed(u, category)}
                self.assertEqual(in_db, in_python)


class SendGatewayTests(TestCase):
    def setUp(self):
        _templates()
        self.user = User.objects.create(username="ellen", first_name="Ellen", email="ellen@example.com",
                                        preferred_language="nl-be")

    def test_queues_a_rendered_mail_in_the_recipients_language(self):
        row = send(self.user, MailCategory.REMINDER, "note", {"extra": "Tot zaterdag"})
        self.assertEqual((row.status, row.recipient, row.language, row.subject), (Status.PENDING, "ellen@example.com", "nl-be", "Hallo Ellen"))
        self.assertIn("Tot zaterdag", row.body)
        self.assertIn("/mail/unsubscribe/", row.body)
        self.assertEqual(row.priority, 5)
        self.assertEqual(len(django_mail.outbox), 0)  # queued, not sent

    def test_mail_that_cant_be_switched_off_has_no_unsubscribe_link(self):
        row = send(self.user, MailCategory.SERVICE, "account")
        self.assertNotIn("/mail/unsubscribe/", row.body)
        self.assertEqual(row.priority, 0)

    def test_suppressed_with_a_reason(self):
        cases = {
            "unsubscribed": lambda: set_preference(self.user, MailCategory.REMINDER, False, ConsentEvent.PREFERENCES),
            "blocked": lambda: EmailSuppression.objects.create(email="Ellen@Example.com ", reason=EmailSuppression.HARD_BOUNCE),
            "no address": lambda: User.objects.filter(pk=self.user.pk).update(email=""),
            "inactive": lambda: User.objects.filter(pk=self.user.pk).update(is_active=False),
        }
        for name, setup in cases.items():
            with self.subTest(name), transaction.atomic():
                setup()
                user = User.objects.get(pk=self.user.pk)
                row = send(user, MailCategory.REMINDER, "note")
                self.assertEqual(row.status, Status.SUPPRESSED)
                self.assertTrue(row.status_reason)
                transaction.set_rollback(True)

    def test_newsletter_needs_an_opt_in(self):
        self.assertEqual(send(self.user, MailCategory.NEWSLETTER, "note").status, Status.SUPPRESSED)
        set_preference(self.user, MailCategory.NEWSLETTER, True, ConsentEvent.SIGNUP)
        self.assertEqual(send(self.user, MailCategory.NEWSLETTER, "note").status, Status.PENDING)

    def test_idempotency_key(self):
        first = send(self.user, MailCategory.REMINDER, "note", idempotency_key="reminder:1:1")
        second = send(self.user, MailCategory.REMINDER, "note", idempotency_key="reminder:1:1")
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(EmailMessage.objects.count(), 1)


class _FakeConnection:
    """Stands in for the SMTP connection: `fail` maps a recipient to the
    exception its send raises."""

    def __init__(self, fail=None):
        self.fail = fail or {}
        self.sent = []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def send_messages(self, messages):
        for message in messages:
            if (error := self.fail.get(message.to[0])) is not None:
                raise error
            self.sent.append(message)
        return len(messages)


@override_settings(MAILING_CLAIM_LIMIT=3, MAILING_BATCH_SIZE=2)
class QueueTests(TestCase):
    def setUp(self):
        _templates()
        self.users = [User.objects.create(username=f"u{i}", email=f"u{i}@example.com") for i in range(4)]

    def _queue(self, user, category=MailCategory.REMINDER, key="note", **kwargs):
        return send(user, category, "account" if category == MailCategory.SERVICE else key, **kwargs)

    def test_claims_by_priority_up_to_the_limit(self):
        reminders = [self._queue(u) for u in self.users[:3]]
        urgent = self._queue(self.users[3], MailCategory.SERVICE)
        later = self._queue(self.users[0], send_after=timezone.now() + timedelta(hours=1))

        claimed = _claim_pending()

        self.assertEqual(claimed[0], urgent.pk)
        self.assertEqual(len(claimed), 3)
        self.assertNotIn(later.pk, claimed)
        self.assertEqual(EmailMessage.objects.get(pk=reminders[2].pk).status, Status.PENDING)
        # Nothing more is claimed while three are in flight.
        self.assertEqual(_claim_pending(), [])

    def test_dispatcher_hands_out_batches(self):
        for user in self.users[:3]:
            self._queue(user)
        with patch("mailing.tasks.group") as fake_group:
            self.assertEqual(send_pending_emails(), 3)
        signatures = list(fake_group.call_args.args[0])
        self.assertEqual([len(sig.args[0]) for sig in signatures], [2, 1])

    def _claimed(self, *rows):
        EmailMessage.objects.filter(pk__in=[r.pk for r in rows]).update(status=Status.SENDING, claimed_at=timezone.now())

    def test_batch_sends_with_message_id_and_unsubscribe_headers(self):
        reminder, account = self._queue(self.users[0]), self._queue(self.users[1], MailCategory.SERVICE)
        self._claimed(reminder, account)
        connection = _FakeConnection()
        with patch("mailing.tasks.mail.get_connection", return_value=connection):
            self.assertEqual(send_email_batch([reminder.pk, account.pk]), 2)

        sent = {m.to[0]: m for m in connection.sent}
        self.assertIn("List-Unsubscribe", sent["u0@example.com"].extra_headers)
        self.assertEqual(sent["u0@example.com"].extra_headers["List-Unsubscribe-Post"], "List-Unsubscribe=One-Click")
        self.assertNotIn("List-Unsubscribe", sent["u1@example.com"].extra_headers)
        for row in EmailMessage.objects.all():
            self.assertEqual((row.status, row.attempts), (Status.SENT, 1))
            self.assertTrue(row.message_id.startswith("<"))
            self.assertEqual(sent[row.recipient].extra_headers["Message-ID"], row.message_id)

    def test_unsubscribe_header_is_a_plain_url_not_an_encoded_word(self):
        from .tasks import _build

        row = self._queue(self.users[0])
        import email.policy

        raw = _build(row)[0].message(policy=email.policy.SMTP).as_bytes().decode()
        header = next(line for line in raw.splitlines() if line.startswith("List-Unsubscribe:"))
        self.assertIn("<https://coolregistration.localhost/mail/unsubscribe/", header)
        self.assertNotIn("=?utf-8?", raw.split("\n\n")[0])

    def test_a_permanent_error_fails_only_that_row(self):
        rows = [self._queue(u) for u in self.users[:2]]
        self._claimed(*rows)
        refused = smtplib.SMTPRecipientsRefused({"u0@example.com": (550, b"no such user")})
        with patch("mailing.tasks.mail.get_connection", return_value=_FakeConnection({"u0@example.com": refused})):
            send_email_batch([r.pk for r in rows])
        statuses = dict(EmailMessage.objects.values_list("recipient", "status"))
        self.assertEqual(statuses, {"u0@example.com": Status.FAILED, "u1@example.com": Status.SENT})

    def test_a_server_problem_is_retried_and_never_resends(self):
        rows = [self._queue(u) for u in self.users[:2]]
        self._claimed(*rows)
        down = smtplib.SMTPServerDisconnected("gone")
        with patch("mailing.tasks.mail.get_connection", return_value=_FakeConnection({"u1@example.com": down})):
            with self.assertRaises(TransientSendError):
                send_email_batch([r.pk for r in rows])
        self.assertEqual(dict(EmailMessage.objects.values_list("recipient", "status")),
                         {"u0@example.com": Status.SENT, "u1@example.com": Status.SENDING})

        connection = _FakeConnection()
        with patch("mailing.tasks.mail.get_connection", return_value=connection):
            send_email_batch([r.pk for r in rows])
        self.assertEqual([m.to[0] for m in connection.sent], ["u1@example.com"])

    def test_after_the_last_retry_the_rest_of_the_batch_fails(self):
        rows = [self._queue(u) for u in self.users[:2]]
        self._claimed(*rows)
        EmailMessage.objects.filter(pk=rows[0].pk).update(status=Status.SENT)
        SendBatchTask().on_failure(RuntimeError("smtp down"), "task-id", ([r.pk for r in rows],), {}, None)
        self.assertEqual(dict(EmailMessage.objects.values_list("recipient", "status")),
                         {"u0@example.com": Status.SENT, "u1@example.com": Status.FAILED})

    @override_settings(MAILING_CLAIM_TIMEOUT_MINUTES=60)
    def test_requeue_stuck_rows(self):
        stuck, fresh = self._queue(self.users[0]), self._queue(self.users[1])
        EmailMessage.objects.filter(pk=stuck.pk).update(status=Status.SENDING, claimed_at=timezone.now() - timedelta(hours=2))
        EmailMessage.objects.filter(pk=fresh.pk).update(status=Status.SENDING, claimed_at=timezone.now())
        self.assertEqual(requeue_stuck_emails(), 1)
        self.assertEqual(dict(EmailMessage.objects.values_list("pk", "status")), {stuck.pk: Status.PENDING, fresh.pk: Status.SENDING})


class MailPreferencesViewTests(TestCase):
    def setUp(self):
        self.parent = User.objects.create(username="parent", email="p@example.com", preferred_language="nl-be")
        Municipality.objects.create(postal_code="9000", name="Gent", center=Point(3.7174, 51.0543, srid=4326))

    def test_login_required(self):
        self.assertEqual(self.client.get(reverse("mail_preferences")).status_code, 302)

    def test_shows_the_explanation_and_the_current_choices(self):
        self.client.force_login(self.parent)
        response = self.client.get(reverse("mail_preferences"))
        self.assertContains(response, "We use what we know about your family")
        form = response.context["form"]
        self.assertTrue(form["category_reminder"].value())
        self.assertFalse(form["category_newsletter"].value())
        self.assertContains(response, 'id="id_category_reminder_helptext"')
        self.assertContains(response, "Always on")

    def test_saving_changes_preferences_language_and_postcode(self):
        self.client.force_login(self.parent)
        response = self.client.post(reverse("mail_preferences"), {
            "category_newsletter": "on", "category_dojo_news": "on", "category_volunteer": "on",
            "preferred_language": "fr-be", "postal_code": "9000",
        })
        self.assertRedirects(response, reverse("mail_preferences"))
        self.assertTrue(is_subscribed(self.parent, MailCategory.NEWSLETTER))
        self.assertFalse(is_subscribed(self.parent, MailCategory.REMINDER))
        self.parent.refresh_from_db()
        self.assertEqual((self.parent.preferred_language, self.parent.postal_code), ("fr-be", "9000"))
        self.assertEqual(set(ConsentEvent.objects.values_list("category", "source")),
                         {("newsletter", "preferences"), ("reminder", "preferences")})

    def test_ninja_account_sees_only_its_own_kinds_of_mail(self):
        teen = User.objects.create(username="teen", email="t@example.com", account_type=User.NINJA)
        self.client.force_login(teen)
        response = self.client.get(reverse("mail_preferences"))
        self.assertNotContains(response, "category_newsletter")
        self.assertNotContains(response, 'name="postal_code"')


class UnsubscribeViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create(username="parent", email="p@example.com")
        set_preference(self.user, MailCategory.NEWSLETTER, True, ConsentEvent.SIGNUP)
        self.url = reverse("mail_unsubscribe", kwargs={"token": unsubscribe_token(self.user, MailCategory.NEWSLETTER)})

    def test_get_asks_for_confirmation_and_changes_nothing(self):
        response = self.client.get(self.url)
        self.assertContains(response, "newsletter and campaigns")
        self.assertTrue(is_subscribed(self.user, MailCategory.NEWSLETTER))

    def test_one_click_post_needs_no_login_or_csrf(self):
        client = Client(enforce_csrf_checks=True)
        response = client.post(self.url, {"List-Unsubscribe": "One-Click"})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(is_subscribed(self.user, MailCategory.NEWSLETTER))
        self.assertTrue(is_subscribed(self.user, MailCategory.REMINDER))
        self.assertEqual(ConsentEvent.objects.latest("id").source, ConsentEvent.UNSUBSCRIBE_LINK)

    def test_unsubscribe_from_everything_optional(self):
        self.client.post(self.url, {"scope": "all"})
        self.assertEqual({c for c, on in preferences_for(self.user).items() if on},
                         {MailCategory.SERVICE, MailCategory.REGISTRATION})

    def test_bad_token_or_category_is_404(self):
        self.assertEqual(self.client.get(reverse("mail_unsubscribe", kwargs={"token": "nope"})).status_code, 404)
        service = reverse("mail_unsubscribe", kwargs={"token": unsubscribe_token(self.user, MailCategory.SERVICE)})
        self.assertEqual(self.client.post(service).status_code, 404)


# --- phase 4: bounces -----------------------------------------------------------


def _dsn(action="failed", status="5.1.1", recipient="u0@example.com", message_id="", to="bounces@example.org"):
    return dsn_report(recipient, message_id=message_id, action=action, status=status, to=to)


def _complaint(recipient="u0@example.com", message_id=""):
    return complaint_report(recipient, message_id=message_id)


class _FakeMailbox:
    """Stands in for ImapMailbox: `messages` maps uid -> raw bytes."""

    messages = {}
    key = "INBOX:1"

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def unprocessed_uids(self):
        seen = set(ProcessedImapMessage.objects.filter(mailbox=self.key).values_list("uid", flat=True))
        return sorted(uid for uid in self.messages if str(uid) not in seen)

    def fetch(self, uid):
        import email as email_lib

        return email_lib.message_from_bytes(self.messages[uid], policy=email_lib.policy.default)


@override_settings(MAILING_BOUNCE_ADDRESS="bounces@example.org")
class BounceTests(TestCase):
    def setUp(self):
        _templates()
        self.user = User.objects.create(username="u0", email="u0@example.com")
        self.row = send(self.user, MailCategory.REMINDER, "note")
        EmailMessage.objects.filter(pk=self.row.pk).update(
            status=Status.SENT, message_id="<123.456.789@coolregistration.localhost>")
        self.row.refresh_from_db()

    def _process(self, *raw_messages, start=1):
        from .bounce import BounceProcessor

        _FakeMailbox.messages = {start + i: raw for i, raw in enumerate(raw_messages)}
        return BounceProcessor(mailbox_class=_FakeMailbox).process()

    def test_hard_bounce_matched_by_message_id(self):
        self._process(_dsn(message_id=self.row.message_id))
        self.row.refresh_from_db()
        self.assertEqual(self.row.status, Status.BOUNCED)
        self.assertEqual(EmailSuppression.objects.get().reason, EmailSuppression.HARD_BOUNCE)
        record = BounceRecord.objects.get()
        self.assertEqual((record.kind, record.status_code, record.message_id), (BounceRecord.HARD, "5.1.1", self.row.pk))
        # The next mail to that address isn't sent.
        self.assertEqual(send(self.user, MailCategory.REMINDER, "note").status, Status.SUPPRESSED)

    def test_each_imap_message_is_handled_once(self):
        self.assertEqual(self._process(_dsn(message_id=self.row.message_id)), 1)
        self.assertEqual(self._process(_dsn(message_id=self.row.message_id)), 0)  # same uid again
        self.assertEqual(BounceRecord.objects.count(), 1)

    @override_settings(MAILING_BOUNCE_ADDRESS="bounces+{id}@example.org")
    def test_matched_by_verp_address(self):
        self._process(_dsn(recipient="u0@example.com", to=f"bounces+{self.row.pk}@example.org"))
        self.assertEqual(BounceRecord.objects.get().message_id, self.row.pk)

    @override_settings(MAILING_SOFT_BOUNCE_LIMIT=3)
    def test_soft_bounces_block_only_after_the_limit(self):
        self._process(_dsn(action="delayed", status="4.2.2"), _dsn(action="delayed", status="4.2.2"))
        self.assertFalse(EmailSuppression.objects.exists())
        self.row.refresh_from_db()
        self.assertEqual(self.row.status, Status.SENT)
        self._process(_dsn(action="delayed", status="4.2.2"), start=3)
        self.assertEqual(EmailSuppression.objects.get().reason, EmailSuppression.SOFT_BOUNCES)

    def test_complaint_switches_off_optional_mail_but_does_not_block(self):
        set_preference(self.user, MailCategory.NEWSLETTER, True, ConsentEvent.SIGNUP)
        self._process(_complaint(message_id=self.row.message_id))
        self.assertEqual({c for c, on in preferences_for(self.user).items() if on},
                         {MailCategory.SERVICE, MailCategory.REGISTRATION})
        self.assertEqual(ConsentEvent.objects.latest("id").source, ConsentEvent.BOUNCE)
        self.assertFalse(EmailSuppression.objects.exists())

    def test_plain_text_bounce_quoting_our_message(self):
        raw = f"""From: postmaster@old.example
To: bounces@example.org
Subject: Mail delivery failed: returning message to sender

A message that you sent could not be delivered.
  u0@example.com: 550 5.1.1 user unknown

------ This is a copy of the message's headers. ------
Message-ID: {self.row.message_id}
""".encode()
        self._process(raw)
        self.assertEqual(BounceRecord.objects.get().kind, BounceRecord.HARD)

    def test_auto_replies_and_other_mail_are_ignored(self):
        auto = f"""From: someone@example.com
To: bounces@example.org
Subject: Out of office
Auto-Submitted: auto-replied
In-Reply-To: {self.row.message_id}

I'm away until Monday.
""".encode()
        other = b"From: a@example.com\nTo: bounces@example.org\nSubject: Hello\n\nJust a mail.\n"
        self.assertEqual(self._process(auto, other), 2)
        self.assertFalse(BounceRecord.objects.exists())
        self.assertEqual(ProcessedImapMessage.objects.count(), 2)

    @override_settings(MAILING_BOUNCE_ADDRESS="bounces+{id}@example.org", DEFAULT_FROM_EMAIL="CoderDojo <noreply@example.org>")
    def test_mail_goes_out_with_the_bounce_address_as_envelope_sender(self):
        from .tasks import _build

        message, _message_id = _build(self.row)
        self.assertEqual(message.from_email, f"bounces+{self.row.pk}@example.org")
        self.assertEqual(message.message()["From"], "CoderDojo <noreply@example.org>")

    @override_settings(MAILING_BOUNCE_IMAP_HOST="mailpit", MAILING_BOUNCE_PROTOCOL="pop3")
    def test_an_unreachable_mailbox_is_a_warning_not_a_crash(self):
        from .tasks import process_bounces

        with patch("mailing.bounce.poplib.POP3", side_effect=ConnectionRefusedError(111, "refused")):
            with self.assertLogs("mailing.tasks", level="WARNING"):
                self.assertEqual(process_bounces(), 0)

    @override_settings(MAILING_BOUNCE_IMAP_HOST="")
    def test_off_without_a_mailbox(self):
        from .tasks import process_bounces

        self.assertEqual(process_bounces(), 0)


@override_settings(MAILING_BOUNCE_IMAP_HOST="imap.example.org", MAILING_BOUNCE_IMAP_MAILBOX="Bounces",
                   MAILING_BOUNCE_IMAP_SSL=True, MAILING_BOUNCE_PROTOCOL="imap")
class ImapMailboxTests(TestCase):
    """ImapMailbox against a mocked imaplib connection (no IMAP server in
    the devcontainer)."""

    def _imap(self):
        from unittest.mock import MagicMock

        imap = MagicMock()
        imap.response.return_value = ("OK", [b"4711"])

        def uid(command, *args):
            if command == "SEARCH":
                return "OK", [b"7"]  # "8:*" still returns the newest message, uid 7
            return "OK", [(b"7 (BODY[] {10}", b"Subject: x\n\nhello\n"), b")"]

        imap.uid.side_effect = uid
        return imap

    def test_key_includes_uidvalidity_and_old_uids_are_skipped(self):
        from .bounce import ImapMailbox

        imap = self._imap()
        with patch("mailing.bounce.imaplib.IMAP4_SSL", return_value=imap):
            with ImapMailbox() as mailbox:
                self.assertEqual(mailbox.key, "Bounces:4711")
                self.assertEqual(mailbox.uids_after(7), [])
                self.assertEqual(mailbox.uids_after(6), [7])
                self.assertEqual(mailbox.fetch(7)["Subject"], "x")
        imap.select.assert_called_once_with("Bounces", readonly=True)
        imap.logout.assert_called_once()


@override_settings(MAILING_BOUNCE_PROTOCOL="pop3", MAILING_BOUNCE_IMAP_HOST="mailpit", MAILING_BOUNCE_IMAP_SSL=False)
class Pop3MailboxTests(TestCase):
    """Pop3Mailbox (Mailpit in the devcontainer) against a mocked poplib."""

    def test_new_messages_are_the_unprocessed_uidls(self):
        from unittest.mock import MagicMock

        from .bounce import BounceProcessor, Pop3Mailbox

        pop = MagicMock()
        pop.uidl.return_value = (b"+OK", [b"1 aaa", b"2 bbb"], 0)
        pop.retr.side_effect = lambda n: (b"+OK", [b"Subject: m%d" % n, b"", b"hi"], 0)
        ProcessedImapMessage.objects.create(mailbox="pop3:mailpit", uid="aaa")

        with patch("mailing.bounce.poplib.POP3", return_value=pop):
            self.assertIs(BounceProcessor().mailbox_class, Pop3Mailbox)
            with Pop3Mailbox() as mailbox:
                self.assertEqual(mailbox.unprocessed_uids(), ["bbb"])
                self.assertEqual(mailbox.fetch("bbb")["Subject"], "m2")
            self.assertEqual(BounceProcessor().process(), 1)
        self.assertTrue(ProcessedImapMessage.objects.filter(mailbox="pop3:mailpit", uid="bbb").exists())
        pop.dele.assert_not_called()


# --- phase 5: automated mail ----------------------------------------------------


class AutomatedMailTests(TestCase):
    def setUp(self):
        call_command("load_mail_templates", stdout=StringIO())
        self.dojo = make_dojo("Ghent")
        self.parent = User.objects.create(username="parent", first_name="Ellen", email="p@example.com",
                                          preferred_language="nl-be")
        self.co_parent = User.objects.create(username="co", email="co@example.com")
        self.teen_login = User.objects.create(username="teen", email="t@example.com", account_type=User.NINJA)
        self.kid = Ninja.objects.create(name="Emma Peeters", account=self.teen_login, home_dojo=self.dojo)
        for guardian in (self.parent, self.co_parent):
            Guardianship.objects.create(guardian=guardian, ninja=self.kid)

    def _event(self, days_ahead=2, status=Event.OPEN, places=10, dojo=None, name="Scratch"):
        start = timezone.now().replace(hour=14, minute=0, second=0, microsecond=0) + timedelta(days=days_ahead)
        return Event.objects.create(name=name, dojo=dojo or self.dojo, status=status, places=places,
                                    start_time=start, end_time=start + timedelta(hours=2))

    def _mails(self, **filters):
        return list(EmailMessage.objects.filter(**filters).order_by("id").values_list("recipient", "template_key", "status"))

    def test_family_is_guardians_and_own_login_with_email(self):
        from .automated import family_of

        User.objects.filter(pk=self.co_parent.pk).update(email="")
        self.assertEqual([u.username for u in family_of(self.kid)], ["parent", "teen"])

    def test_signup_confirms_to_the_whole_family(self):
        event = self._event(days_ahead=10)
        self.client.force_login(self.parent)
        self.client.post(reverse("event_signup", kwargs={"event_id": event.id}),
                         {"child": [str(self.kid.id)], "child_order": str(self.kid.id)})
        self.assertEqual(self._mails(), [
            ("p@example.com", "registration_confirmed", Status.PENDING),
            ("co@example.com", "registration_confirmed", Status.PENDING),
            ("t@example.com", "registration_confirmed", Status.PENDING),
        ])
        dutch = EmailMessage.objects.get(recipient="p@example.com")
        self.assertEqual(dutch.subject, "Emma is ingeschreven voor Scratch")

    def test_signup_for_a_full_session_sends_the_waiting_list_notice(self):
        event = self._event(days_ahead=10, places=0)
        self.client.force_login(self.parent)
        self.client.post(reverse("event_signup", kwargs={"event_id": event.id}),
                         {"child": [str(self.kid.id)], "child_order": str(self.kid.id)})
        self.assertEqual({key for _r, key, _s in self._mails()}, {"registration_waitlisted"})

    def test_moving_up_from_the_waiting_list_mails_the_family(self):
        event = self._event(days_ahead=10, places=1)
        other_parent = User.objects.create(username="other", email="o@example.com")
        other_kid = Ninja.objects.create(name="Liam")
        Guardianship.objects.create(guardian=other_parent, ninja=other_kid)
        confirmed = Registration.objects.create(event=event, ninja=other_kid, waiting_list=False, position=1)
        Registration.objects.create(event=event, ninja=self.kid, waiting_list=True, position=2)

        self.client.force_login(other_parent)
        self.client.post(reverse("cancel_registration", kwargs={"registration_id": confirmed.id}))

        self.assertEqual({(r, k) for r, k, _s in self._mails()},
                         {("p@example.com", "waitlist_promoted"), ("co@example.com", "waitlist_promoted"),
                          ("t@example.com", "waitlist_promoted")})

    def test_a_missing_template_never_breaks_a_signup(self):
        EmailTemplate.objects.all().delete()
        event = self._event(days_ahead=10)
        self.client.force_login(self.parent)
        with self.assertLogs("mailing.automated", level="ERROR"):
            self.client.post(reverse("event_signup", kwargs={"event_id": event.id}),
                             {"child": [str(self.kid.id)], "child_order": str(self.kid.id)})
        self.assertTrue(Registration.objects.filter(event=event, ninja=self.kid).exists())
        self.assertEqual(EmailMessage.objects.count(), 0)

    def test_session_reminders_two_days_before_once(self):
        from .automated import send_session_reminders

        in_two_days, in_three_days = self._event(2), self._event(3, name="Later")
        waitlisted_kid = Ninja.objects.create(name="Waitlisted")
        Guardianship.objects.create(guardian=self.co_parent, ninja=waitlisted_kid)
        Registration.objects.create(event=in_two_days, ninja=self.kid, waiting_list=False, position=1)
        Registration.objects.create(event=in_two_days, ninja=waitlisted_kid, waiting_list=True, position=2)
        Registration.objects.create(event=in_three_days, ninja=self.kid, waiting_list=False, position=1)
        set_preference(self.teen_login, MailCategory.REMINDER, False, ConsentEvent.PREFERENCES)

        self.assertEqual(send_session_reminders(), 2)  # parent + co-parent; the teen opted out
        self.assertEqual(send_session_reminders(), 0)  # idempotent
        self.assertEqual(self._mails(template_key="session_reminder"), [
            ("p@example.com", "session_reminder", Status.PENDING),
            ("co@example.com", "session_reminder", Status.PENDING),
            ("t@example.com", "session_reminder", Status.SUPPRESSED),
        ])

    def test_new_sessions_digest_per_family_and_dojo(self):
        from .automated import announce_new_sessions

        other_dojo = make_dojo("Antwerp")
        a, b = self._event(10, name="A"), self._event(17, name="B")
        self._event(12, dojo=other_dojo, name="Elsewhere")
        self._event(20, status=Event.DRAFT, name="Draft")
        # A family whose child came to a session at this dojo also hears about it.
        visitor = User.objects.create(username="visitor", email="v@example.com")
        visiting_kid = Ninja.objects.create(name="Visitor", home_dojo=other_dojo)
        Guardianship.objects.create(guardian=visitor, ninja=visiting_kid)
        past = self._event(-30, status=Event.CLOSED, name="Past")
        Registration.objects.create(event=past, ninja=visiting_kid, waiting_list=False, position=1, attended=True)

        announce_new_sessions()

        ghent = EmailMessage.objects.filter(template_key="new_sessions_at_dojo", body__contains="Ghent")
        self.assertEqual(set(ghent.values_list("recipient", flat=True)),
                         {"p@example.com", "co@example.com", "t@example.com", "v@example.com"})
        body = ghent.get(recipient="co@example.com").body
        self.assertIn("A,", body)
        self.assertIn("B,", body)
        self.assertNotIn("Elsewhere", body)
        self.assertIsNotNone(Event.objects.get(pk=a.pk).announced_at)
        self.assertIsNotNone(Event.objects.get(pk=b.pk).announced_at)
        count = EmailMessage.objects.count()
        announce_new_sessions()
        self.assertEqual(EmailMessage.objects.count(), count)

    def test_published_at_is_set_the_first_time_a_session_opens(self):
        event = self._event(10, status=Event.DRAFT)
        self.assertIsNone(event.published_at)
        event.status = Event.OPEN
        event.save(update_fields=["status"])
        first = Event.objects.get(pk=event.pk).published_at
        self.assertIsNotNone(first)
        event.status = Event.CLOSED
        event.save(update_fields=["status"])
        event.status = Event.OPEN
        event.save(update_fields=["status"])
        self.assertEqual(Event.objects.get(pk=event.pk).published_at, first)

    def test_load_mail_templates_never_overwrites(self):
        EmailTemplate.objects.filter(key="session_reminder", language="en-us").update(subject="Edited")
        call_command("load_mail_templates", stdout=StringIO())
        self.assertEqual(EmailTemplate.objects.get(key="session_reminder", language="en-us").subject, "Edited")


class EveryMailGoesThroughTheEngineTests(TestCase):
    """Guard for the rule "every mail goes through mailing.services.send":
    only the engine's own sender (mailing/tasks.py) may hand mail to
    Django's mail backend."""

    DIRECT_SEND = re.compile(
        r"(?<!def )\b(send_mail|send_mass_mail|mail_admins|mail_managers)\(|EmailMultiAlternatives\(|\.send_messages\("
    )
    ALLOWED = {"mailing/tasks.py", "mailing/management/commands/simulate_bounce.py"}

    def test_no_direct_mail_sending_outside_the_engine(self):
        from pathlib import Path

        from django.conf import settings

        root = Path(settings.BASE_DIR)
        offenders = []
        for path in root.rglob("*.py"):
            relative = path.relative_to(root).as_posix()
            if (relative in self.ALLOWED or "/migrations/" in relative or relative.endswith("tests.py")
                    or relative.startswith((".", "docs/", "static/", "media/"))):
                continue
            for number, line in enumerate(path.read_text(errors="ignore").splitlines(), 1):
                if self.DIRECT_SEND.search(line) and not line.lstrip().startswith("#"):
                    offenders.append(f"{relative}:{number}: {line.strip()}")
        self.assertEqual(offenders, [], "send mail through mailing.services.send() instead")


# --- phase 8: campaigns from the organisation dashboard ---------------------------


class CampaignDashboardTests(TestCase):
    def setUp(self):
        from accounts.models import OrganisationRole

        call_command("load_mail_templates", stdout=StringIO())
        self.admin = User.objects.create(username="orgadmin", first_name="Ann", email="ann@example.com")
        OrganisationRole.objects.create(account=self.admin, role=OrganisationRole.ADMIN)
        self.girl_family = _family("girlfam", Ninja.GIRL, email="g@example.com")
        self.boy_family = _family("boyfam", Ninja.BOY, email="b@example.com")
        for family in (self.girl_family, self.boy_family):
            set_preference(family, MailCategory.NEWSLETTER, True, ConsentEvent.SIGNUP)
        self.segment = _segment(("ninja", "and", [("ninja_gender", "in", [Ninja.GIRL])]))
        self.segment.name = "Girls"
        self.segment.save()
        self.client.force_login(self.admin)

    def _campaign(self, **fields):
        return Campaign.objects.create(**{
            "name": "Girlz", "segment": self.segment, "template_key": "campaign_girlz",
            "context": {"signup_url": "https://example.org"}, **fields,
        })

    # access

    def test_only_the_organisation_admin_role_gets_in(self):
        from accounts.models import OrganisationRole

        urls = [reverse("manage_campaign_list"), reverse("manage_segment_list"), reverse("manage_campaign_create")]
        self.client.logout()
        for url in urls:
            self.assertEqual(self.client.get(url).status_code, 302)  # to login
        board = User.objects.create(username="board", email="bo@example.com")
        OrganisationRole.objects.create(account=board, role=OrganisationRole.BOARD)
        for user in (board, self.girl_family):
            self.client.force_login(user)
            for url in urls:
                self.assertEqual(self.client.get(url).status_code, 404)
        self.client.force_login(self.admin)
        for url in urls:
            self.assertEqual(self.client.get(url).status_code, 200)

    def test_nav_links_admins_to_the_dashboard_and_the_board_to_the_admin(self):
        from accounts.models import OrganisationRole

        self.assertContains(self.client.get(reverse("account_home")), f'href="{reverse("manage_home")}"')
        board = User.objects.create(username="board", email="bo@example.com")
        OrganisationRole.objects.create(account=board, role=OrganisationRole.BOARD)
        self.client.force_login(board)
        response = self.client.get(reverse("account_home"))
        self.assertNotContains(response, f'href="{reverse("manage_home")}"')
        self.assertContains(response, 'href="/admin/"')

    # the draft

    def test_create_a_draft_with_template_variables(self):
        response = self.client.post(reverse("manage_campaign_create"), {
            "name": "Girlz spring", "category": "newsletter", "template_key": "campaign_girlz",
            "segment": self.segment.pk, "variables": "signup_url: https://example.org/girlz\n\n", "scheduled_at": "",
        })
        campaign = Campaign.objects.get(name="Girlz spring")
        self.assertRedirects(response, reverse("manage_campaign_detail", kwargs={"campaign_id": campaign.pk}))
        self.assertEqual(campaign.context, {"signup_url": "https://example.org/girlz"})
        self.assertEqual(campaign.status, Campaign.Status.DRAFT)

    def test_form_only_offers_mail_people_can_switch_off_and_future_times(self):
        from .forms import CampaignForm

        form = CampaignForm()
        self.assertNotIn("service", dict(form.fields["category"].choices))
        self.assertNotIn("registration", dict(form.fields["category"].choices))
        bad = CampaignForm({"name": "x", "category": "newsletter", "template_key": "campaign_girlz",
                            "segment": self.segment.pk, "variables": "Bad Name: x",
                            "scheduled_at": "2001-01-01T10:00"})
        self.assertFalse(bad.is_valid())
        self.assertIn("variables", bad.errors)
        self.assertIn("scheduled_at", bad.errors)

    def test_detail_shows_preview_in_every_language_and_the_audience(self):
        campaign = self._campaign()
        response = self.client.get(reverse("manage_campaign_detail", kwargs={"campaign_id": campaign.pk}))
        self.assertEqual(len(response.context["previews"]), 3)
        self.assertContains(response, "https://example.org")
        self.assertEqual(response.context["stats"]["audience"], 1)
        self.assertContains(response, "g@example.com")
        self.assertNotContains(response, "b@example.com")

    def test_test_mail_goes_to_the_author_whatever_their_preferences(self):
        campaign = self._campaign()
        self.client.post(reverse("manage_campaign_test", kwargs={"campaign_id": campaign.pk}))
        row = EmailMessage.objects.get(is_test=True)
        self.assertEqual((row.recipient, row.status), ("ann@example.com", Status.PENDING))
        self.assertTrue(row.subject.startswith("[Test] "))
        # Not dropped at send time either, although Ann never opted in.
        EmailMessage.objects.filter(pk=row.pk).update(status=Status.SENDING)
        with patch("mailing.tasks.mail.get_connection", return_value=_FakeConnection()):
            send_email_batch([row.pk])
        self.assertEqual(EmailMessage.objects.get(pk=row.pk).status, Status.SENT)
        self.assertEqual(campaigns.stats(campaign)["queued"], 0)  # tests don't count

    # launching

    def test_launch_refuses_what_can_not_go_out(self):
        for fields, problem in [
            ({"segment": None}, "Pick a segment"),
            ({"template_key": "nope"}, "no English template"),
            ({"category": "service"}, "switch off"),
        ]:
            with self.subTest(problem):
                campaign = self._campaign(**fields)
                response = self.client.post(reverse("manage_campaign_launch", kwargs={"campaign_id": campaign.pk}), follow=True)
                self.assertContains(response, problem)
                self.assertEqual(Campaign.objects.get(pk=campaign.pk).status, Campaign.Status.DRAFT)

    def test_launch_freezes_the_segment_and_queues_only_those_who_want_it(self):
        campaign = self._campaign()
        extra_girl_family = _family("unsubscribed", Ninja.GIRL, email="u@example.com")  # never opted in
        self.client.post(reverse("manage_campaign_launch", kwargs={"campaign_id": campaign.pk}))
        campaign.refresh_from_db()
        self.assertEqual((campaign.status, campaign.launched_by), (Campaign.Status.QUEUED, self.admin))
        self.assertEqual(campaign.segment_snapshot["groups"][0]["rules"][0]["attribute"], "ninja_gender")

        # Editing the segment afterwards changes nothing for this campaign.
        SegmentRule.objects.filter(group__segment=self.segment).update(value=[Ninja.BOY])
        with patch("mailing.tasks.launch_campaign.delay") as delay:
            campaigns.launch_due()
        delay.assert_called_once_with(campaign.pk)
        self.assertEqual(campaigns.queue_mail(campaign.pk), 1)
        self.assertEqual(list(EmailMessage.objects.values_list("recipient", flat=True)), ["g@example.com"])
        self.assertNotEqual(extra_girl_family.email, "")
        # Safe to run again: nothing new.
        Campaign.objects.filter(pk=campaign.pk).update(queued_at=None)
        self.assertEqual(campaigns.queue_mail(campaign.pk), 0)
        self.assertEqual(Campaign.objects.get(pk=campaign.pk).status, Campaign.Status.SENDING)

        # Completed once everything is out.
        EmailMessage.objects.update(status=Status.SENT)
        campaigns.launch_due()
        self.assertEqual(Campaign.objects.get(pk=campaign.pk).status, Campaign.Status.COMPLETED)
        # A launched campaign can't be edited any more.
        response = self.client.post(reverse("manage_campaign_detail", kwargs={"campaign_id": campaign.pk}), {"name": "Changed"})
        self.assertIsNone(response.context["form"])
        self.assertEqual(Campaign.objects.get(pk=campaign.pk).name, "Girlz")

    def test_a_scheduled_campaign_waits_for_its_time(self):
        later = timezone.now() + timedelta(hours=3)
        campaign = self._campaign(scheduled_at=later)
        campaigns.launch(campaign, self.admin)
        with patch("mailing.tasks.launch_campaign.delay") as delay:
            campaigns.launch_due()
            delay.assert_not_called()
            campaigns.launch_due(now=later + timedelta(minutes=1))
            delay.assert_called_once_with(campaign.pk)

    def test_cancel_withdraws_mail_that_has_not_gone_out(self):
        campaign = self._campaign()
        campaigns.launch(campaign, self.admin)
        campaigns.queue_mail(campaign.pk)
        self.client.post(reverse("manage_campaign_cancel", kwargs={"campaign_id": campaign.pk}))
        self.assertEqual(Campaign.objects.get(pk=campaign.pk).status, Campaign.Status.CANCELLED)
        self.assertEqual(set(EmailMessage.objects.values_list("status", flat=True)), {Status.SUPPRESSED})

    def test_unsubscribing_after_queuing_stops_the_mail_and_shows_in_the_results(self):
        campaign = self._campaign()
        campaigns.launch(campaign, self.admin)
        campaigns.queue_mail(campaign.pk)
        set_preference(self.girl_family, MailCategory.NEWSLETTER, False, ConsentEvent.UNSUBSCRIBE_LINK)
        row = EmailMessage.objects.get()
        EmailMessage.objects.filter(pk=row.pk).update(status=Status.SENDING)
        with patch("mailing.tasks.mail.get_connection", return_value=_FakeConnection()) as connection:
            send_email_batch([row.pk])
        self.assertEqual(EmailMessage.objects.get(pk=row.pk).status, Status.SUPPRESSED)
        self.assertEqual(connection.return_value.sent, [])
        self.assertEqual(campaigns.stats(campaign)["unsubscribed"], 1)


class SegmentBuilderTests(TestCase):
    def setUp(self):
        from accounts.models import OrganisationRole

        self.admin = User.objects.create(username="orgadmin", email="ann@example.com")
        OrganisationRole.objects.create(account=self.admin, role=OrganisationRole.ADMIN)
        self.client.force_login(self.admin)
        _family("girlfam", Ninja.GIRL)
        _family("boyfam", Ninja.BOY)
        _family("unlisted", Ninja.UNSPECIFIED)
        self.client.post(reverse("manage_segment_create"), {"name": "Girlz", "description": "", "is_active": "on"})
        self.segment = Segment.objects.get(name="Girlz")
        self.url = reverse("manage_segment_detail", kwargs={"segment_id": self.segment.pk})

    def _add_group(self, scope, parent=None):
        self.client.post(reverse("manage_segment_add_group", kwargs={"segment_id": self.segment.pk}),
                         {"scope": scope, **({"parent": parent.pk} if parent else {})})
        return SegmentGroup.objects.filter(segment=self.segment).latest("id")

    def _add_rule(self, group, data):
        return self.client.post(
            reverse("manage_segment_add_rule", kwargs={"segment_id": self.segment.pk, "group_id": group.pk}),
            data, follow=True,
        )

    def test_build_a_segment_and_see_its_audience(self):
        group = self._add_group("ninja")
        response = self._add_rule(group, {"attribute": "ninja_gender", "operator": "in", "value": ["girl", "unspecified"]})
        self.assertContains(response, "Child&#x27;s gender is one of Girl, Prefer not to say")
        rule = SegmentRule.objects.get()
        self.assertEqual(rule.value, ["girl", "unspecified"])
        response = self.client.get(self.url)
        self.assertEqual(response.context["count"], 2)
        self.assertContains(response, "girlfam@example.com")
        self.assertNotContains(response, "boyfam@example.com")

    def test_typed_values_for_days_and_distance(self):
        dojo = make_dojo("Ghent", location=Point(3.72, 51.05, srid=4326))
        ninja_group, user_group = self._add_group("ninja"), self._add_group("user")
        self._add_rule(ninja_group, {"attribute": "attended_within_days", "operator": "within_days", "value": "180"})
        self._add_rule(user_group, {"attribute": "near_dojo", "operator": "within", "dojo": str(dojo.pk), "km": "25"})
        values = dict(SegmentRule.objects.values_list("attribute", "value"))
        self.assertEqual(values, {"attended_within_days": 180, "near_dojo": {"dojo": dojo.pk, "km": 25.0}})
        self.assertContains(self.client.get(self.url), "Lives within 25.0 km of Ghent")

    def test_a_rule_that_can_not_work_is_refused_with_a_message(self):
        group = self._add_group("ninja")
        response = self._add_rule(group, {"attribute": "ninja_gender", "operator": "in"})  # nothing ticked
        self.assertContains(response, "non-empty list")
        response = self._add_rule(group, {"attribute": "account_type", "operator": "in", "value": ["adult"]})
        self.assertContains(response, "can&#x27;t be used in a group about")
        self.assertFalse(SegmentRule.objects.exists())

    def test_nested_groups_follow_the_scope_rules(self):
        user_group = self._add_group("user")
        child = self._add_group("ninja", parent=user_group)
        self.assertEqual(child.parent, user_group)
        response = self.client.post(reverse("manage_segment_add_group", kwargs={"segment_id": self.segment.pk}),
                                    {"scope": "user", "parent": child.pk}, follow=True)
        self.assertContains(response, "must also be about the child")
        self.assertEqual(SegmentGroup.objects.filter(parent=child).count(), 0)

    def test_rule_fields_fit_the_attribute(self):
        group = self._add_group("ninja")
        fields_url = reverse("manage_segment_rule_fields", kwargs={"segment_id": self.segment.pk, "group_id": group.pk})
        gender = self.client.get(fields_url, {"attribute": "ninja_gender"})
        self.assertContains(gender, 'type="checkbox" name="value" value="girl"')
        self.assertNotContains(gender, 'value="equals"')
        days = self.client.get(fields_url, {"attribute": "attended_within_days"})
        self.assertContains(days, 'type="number" name="value"')

    def test_change_operator_remove_rule_group_and_segment(self):
        group = self._add_group("ninja")
        self._add_rule(group, {"attribute": "ninja_gender", "operator": "in", "value": ["girl"]})
        self.client.post(reverse("manage_segment_update_group", kwargs={"segment_id": self.segment.pk, "group_id": group.pk}),
                         {"operator": "or"})
        self.assertEqual(SegmentGroup.objects.get(pk=group.pk).operator, "or")
        rule = SegmentRule.objects.get()
        self.client.post(reverse("manage_segment_delete_rule", kwargs={"segment_id": self.segment.pk, "rule_id": rule.pk}))
        self.assertFalse(SegmentRule.objects.exists())
        self.client.post(reverse("manage_segment_delete_group", kwargs={"segment_id": self.segment.pk, "group_id": group.pk}))
        self.assertFalse(SegmentGroup.objects.exists())
        self.client.post(reverse("manage_segment_delete", kwargs={"segment_id": self.segment.pk}))
        self.assertFalse(Segment.objects.exists())

    def test_builder_endpoints_are_404_without_the_admin_role(self):
        group = self._add_group("ninja")
        self.client.force_login(User.objects.get(username="girlfam"))
        for url in [self.url, reverse("manage_segment_add_group", kwargs={"segment_id": self.segment.pk}),
                    reverse("manage_segment_add_rule", kwargs={"segment_id": self.segment.pk, "group_id": group.pk})]:
            self.assertEqual(self.client.post(url, {"scope": "user"}).status_code, 404)


class EngagementAttributeTests(TestCase):
    """Segments on the nightly engagement snapshot (events.engagement)."""

    def setUp(self):
        from events.engagement import rebuild

        self.ghent, self.antwerp = make_dojo("Ghent"), make_dojo("Antwerp", status=Dojo.DORMANT)
        self.regular = _family("regularfam", Ninja.GIRL)
        self.lapsed = _family("lapsedfam", Ninja.BOY)
        regular_kid = Ninja.objects.of_guardian(self.regular).get()
        lapsed_kid = Ninja.objects.of_guardian(self.lapsed).get()
        Ninja.objects.filter(pk=lapsed_kid.pk).update(home_dojo=self.antwerp)
        for days in (150, 120, 90, 60, 30):
            Registration.objects.create(event=self._session(days, self.ghent), ninja=regular_kid,
                                        waiting_list=False, position=1, attended=True)
        for days in (330, 300, 270):
            Registration.objects.create(event=self._session(days, self.antwerp), ninja=lapsed_kid,
                                        waiting_list=False, position=1, attended=True)
        upcoming = self._session(-7, self.ghent, status=Event.OPEN)
        Registration.objects.create(event=upcoming, ninja=regular_kid, waiting_list=False, position=1)
        rebuild()

    def _session(self, days_ago, dojo, status=Event.CLOSED):
        start = timezone.now() - timedelta(days=days_ago)
        return Event.objects.create(name=f"S{days_ago}", dojo=dojo, status=status, places=20,
                                    start_time=start, end_time=start + timedelta(hours=2))

    def _one(self, attribute, operator, value):
        return _resolve(_segment(("ninja", "and", [(attribute, operator, value)])))

    def test_each_engagement_attribute(self):
        self.assertEqual(self._one("engagement_stage", "in", ["regular"]), {"regularfam"})
        self.assertEqual(self._one("engagement_stage", "in", ["lapsed"]), {"lapsedfam"})
        self.assertEqual(self._one("engagement_stage_at_dojo", "in", {"dojo": self.ghent.pk, "stages": ["regular"]}),
                         {"regularfam"})
        self.assertEqual(self._one("attendance_rate", "gte", 50), {"regularfam"})
        self.assertEqual(self._one("sessions_attended", "gte", 3), {"regularfam"})
        self.assertEqual(self._one("days_since_last_visit", "gte", 200), {"lapsedfam"})
        self.assertEqual(self._one("days_since_last_visit", "lte", 45), {"regularfam"})
        self.assertEqual(self._one("has_upcoming_registration", "is", True), {"regularfam"})
        self.assertEqual(self._one("main_dojo_status", "in", ["dormant"]), {"lapsedfam"})

    def test_rules_read_as_sentences_and_validate(self):
        from .segmentation.registry import get_attribute

        self.assertEqual(get_attribute("attendance_rate").describe("gte", 50),
                         "Share of their sessions they came to (last 180 days, %) at least 50%")
        self.assertEqual(get_attribute("engagement_stage_at_dojo").describe("in", {"dojo": self.ghent.pk, "stages": ["at_risk"]}),
                         "At Ghent: At risk")
        with self.assertRaises(ValueError):
            get_attribute("missed_in_a_row").validate("gte", -1)
        with self.assertRaises(ValueError):
            get_attribute("engagement_stage_at_dojo").validate("in", {"dojo": self.ghent.pk, "stages": []})

    def test_builder_widgets_and_parsing(self):
        from accounts.models import OrganisationRole

        admin = User.objects.create(username="orgadmin", email="ann@example.com")
        OrganisationRole.objects.create(account=admin, role=OrganisationRole.ADMIN)
        self.client.force_login(admin)
        segment = Segment.objects.create(name="Engaged")
        group = SegmentGroup.objects.create(segment=segment, scope="ninja")
        fields = reverse("manage_segment_rule_fields", kwargs={"segment_id": segment.pk, "group_id": group.pk})
        self.assertContains(self.client.get(fields, {"attribute": "missed_in_a_row"}), 'step="any"')
        self.assertContains(self.client.get(fields, {"attribute": "engagement_stage_at_dojo"}), 'name="dojo"')
        add = reverse("manage_segment_add_rule", kwargs={"segment_id": segment.pk, "group_id": group.pk})
        self.client.post(add, {"attribute": "missed_in_a_row", "operator": "gte", "value": "3"})
        self.client.post(add, {"attribute": "engagement_stage_at_dojo", "operator": "in", "dojo": str(self.ghent.pk),
                               "value": ["at_risk", "lapsed"]})
        self.assertEqual(dict(SegmentRule.objects.values_list("attribute", "value")), {
            "missed_in_a_row": 3,
            "engagement_stage_at_dojo": {"dojo": self.ghent.pk, "stages": ["at_risk", "lapsed"]},
        })


class ProfileAttributeTests(TestCase):
    """Tier 1 attributes read straight from the site's data."""

    def setUp(self):
        from events.models import Belt, NinjaBelt

        today = timezone.localdate()
        self.dojo = make_dojo("Ghent")
        self.ten = _family("tenfam", Ninja.GIRL)
        self.fifteen = _family("fifteenfam", Ninja.BOY)
        Ninja.objects.filter(guardianships__guardian=self.ten).update(
            date_of_birth=today.replace(year=today.year - 10), home_dojo=self.dojo)
        Ninja.objects.filter(guardianships__guardian=self.fifteen).update(date_of_birth=today.replace(year=today.year - 15))
        yellow = Belt.objects.create(level=2, name="Yellow")
        NinjaBelt.objects.create(ninja=Ninja.objects.of_guardian(self.fifteen).get(), belt=yellow, awarded_on=today)
        self.champion = User.objects.create(username="champ", email="c@example.com")
        add_member(self.dojo, self.champion, DojoMembership.CHAMPION)

    def _one(self, scope, attribute, operator, value):
        return _resolve(_segment((scope, "and", [(attribute, operator, value)])))

    def test_age_home_dojo_and_belt(self):
        self.assertEqual(self._one("ninja", "ninja_age", "gte", 10), {"tenfam", "fifteenfam"})
        self.assertEqual(self._one("ninja", "ninja_age", "lte", 10), {"tenfam"})
        self.assertEqual(self._one("ninja", "ninja_age", "gte", 11), {"fifteenfam"})
        self.assertEqual(self._one("ninja", "ninja_home_dojo", "in", [self.dojo.pk]), {"tenfam"})
        self.assertEqual(self._one("ninja", "current_belt", "in", [0]), {"tenfam"})
        self.assertEqual(self._one("ninja", "current_belt", "in", [2]), {"fifteenfam"})

    def test_roles_and_new_accounts(self):
        self.assertEqual(self._one("user", "account_role", "in", ["champion"]), {"champ"})
        self.assertEqual(self._one("user", "account_role", "in", ["guardian"]), {"tenfam", "fifteenfam"})
        self.assertEqual(self._one("user", "account_role", "not_in", ["guardian"]), {"champ"})
        User.objects.filter(username="champ").update(date_joined=timezone.now() - timedelta(days=400))
        self.assertEqual(self._one("user", "joined_within_days", "within_days", 30), {"tenfam", "fifteenfam"})

    def test_waiting_list_and_cancellations(self):
        start = timezone.now() + timedelta(days=5)
        event = Event.objects.create(name="Full", dojo=self.dojo, status=Event.OPEN, places=0,
                                     start_time=start, end_time=start + timedelta(hours=2))
        ten_kid = Ninja.objects.of_guardian(self.ten).get()
        registration = Registration.objects.create(event=event, ninja=ten_kid, waiting_list=True, position=1)
        self.assertEqual(self._one("ninja", "waitlisted_for_event", "in", [event.pk]), {"tenfam"})

        self.client.force_login(self.ten)
        self.client.post(reverse("cancel_registration", kwargs={"registration_id": registration.pk}))
        from events.models import RegistrationCancellation

        logged = RegistrationCancellation.objects.get()
        self.assertEqual((logged.ninja, logged.event, logged.was_waitlisted, logged.cancelled_by),
                         (ten_kid, event, True, self.ten))
        self.assertIsNotNone(logged.signed_up_at)
        self.assertEqual(self._one("ninja", "cancellations", "gte", 1), {"tenfam"})
        self.assertEqual(self._one("ninja", "cancellations", "lte", 0), {"fifteenfam"})


class TemplateDashboardTests(TestCase):
    def setUp(self):
        from accounts.models import OrganisationRole

        call_command("load_mail_templates", stdout=StringIO())
        self.admin = User.objects.create(username="orgadmin", email="ann@example.com")
        OrganisationRole.objects.create(account=self.admin, role=OrganisationRole.ADMIN)
        self.client.force_login(self.admin)

    def _edit(self, key, language="en-us"):
        return reverse("manage_template_edit", kwargs={"key": key, "language": language})

    def test_list_shows_what_uses_each_template(self):
        Campaign.objects.create(name="Spring Girlz", template_key="campaign_girlz")
        response = self.client.get(reverse("manage_template_list"))
        self.assertContains(response, "Sent by the site")
        self.assertContains(response, "Spring Girlz")
        self.client.force_login(User.objects.create(username="parent", email="p@example.com"))
        self.assertEqual(self.client.get(reverse("manage_template_list")).status_code, 404)

    def test_edit_a_language_with_preview(self):
        response = self.client.get(self._edit("session_reminder", "nl-be"))
        self.assertContains(response, "Herinnering: Scratch for beginners op zaterdag")
        response = self.client.post(self._edit("session_reminder", "nl-be"), {
            "subject": "Tot {{ start_time|date:'l' }}!", "body": "Hallo {{ recipient_name }}", "description": "d",
        })
        self.assertRedirects(response, self._edit("session_reminder", "nl-be"))
        self.assertEqual(EmailTemplate.objects.get(key="session_reminder", language="nl-be").subject,
                         "Tot {{ start_time|date:'l' }}!")

    def test_a_broken_template_is_refused(self):
        response = self.client.post(self._edit("session_reminder"), {"subject": "Hi", "body": "{% if %}", "description": ""})
        self.assertContains(response, "doesn&#x27;t work as a template")
        self.assertNotEqual(EmailTemplate.objects.get(key="session_reminder", language="en-us").body, "{% if %}")

    def test_write_a_missing_language_starting_from_english(self):
        EmailTemplate.objects.filter(key="campaign_girlz", language="fr-be").delete()
        response = self.client.get(self._edit("campaign_girlz", "fr-be"))
        self.assertContains(response, "no Français (Belgique) version yet")
        self.assertEqual(response.context["form"]["subject"].value(),
                         EmailTemplate.objects.get(key="campaign_girlz", language="en-us").subject)
        self.client.post(self._edit("campaign_girlz", "fr-be"), {"subject": "CoderDojo Girlz", "body": "Salut !", "description": ""})
        self.assertTrue(EmailTemplate.objects.filter(key="campaign_girlz", language="fr-be").exists())

    def test_create_a_campaign_template(self):
        response = self.client.post(reverse("manage_template_create"),
                                    {"key": "campaign_summer", "category": "newsletter", "description": ""})
        self.assertRedirects(response, self._edit("campaign_summer"))
        self.assertEqual(EmailTemplate.objects.get(key="campaign_summer").language, "en-us")
        response = self.client.post(reverse("manage_template_create"),
                                    {"key": "campaign_summer", "category": "newsletter", "description": ""})
        self.assertContains(response, "already exists")

    def test_what_can_and_can_not_be_deleted(self):
        delete_key = lambda key: reverse("manage_template_delete", kwargs={"key": key})  # noqa: E731
        delete_language = lambda key, lang: reverse(  # noqa: E731
            "manage_template_delete_language", kwargs={"key": key, "language": lang})

        self.client.post(delete_language("campaign_girlz", "en-us"))
        self.assertTrue(EmailTemplate.objects.filter(key="campaign_girlz", language="en-us").exists())
        self.client.post(delete_language("campaign_girlz", "fr-be"))
        self.assertFalse(EmailTemplate.objects.filter(key="campaign_girlz", language="fr-be").exists())

        self.client.post(delete_key("password_reset"))
        self.assertTrue(EmailTemplate.objects.filter(key="password_reset").exists())

        Campaign.objects.create(name="Draft", template_key="campaign_new_dojo")
        self.client.post(delete_key("campaign_new_dojo"))
        self.assertTrue(EmailTemplate.objects.filter(key="campaign_new_dojo").exists())

        self.client.post(delete_key("campaign_girlz"))
        self.assertFalse(EmailTemplate.objects.filter(key="campaign_girlz").exists())


# --- phase 9: change over time, journeys -------------------------------------------


class Tier3Tests(TestCase):
    def setUp(self):
        call_command("load_mail_templates", stdout=StringIO())
        self.dojo = make_dojo("Ghent")
        self.family = _family("fam", Ninja.GIRL)
        self.kid = Ninja.objects.of_guardian(self.family).get()
        self.other = _family("other", Ninja.BOY)

    def _session(self, days_ago):
        start = timezone.now() - timedelta(days=days_ago)
        return Event.objects.create(name=f"S{days_ago}", dojo=self.dojo, status=Event.CLOSED, places=20,
                                    start_time=start, end_time=start + timedelta(hours=2))

    def test_rebuild_records_stage_changes_once_a_day(self):
        from events.engagement import rebuild
        from events.models import NinjaEngagementChange

        for days in (170, 150, 130, 110):
            Registration.objects.create(event=self._session(days), ninja=self.kid, waiting_list=False, position=1,
                                        attended=True)
        rebuild()
        self.assertFalse(NinjaEngagementChange.objects.exists())  # the first build records nothing
        for days in (60, 40, 20):
            self._session(days)
        rebuild()
        rebuild()
        change = NinjaEngagementChange.objects.get(ninja=self.kid)
        self.assertEqual(change.to_stage, "at_risk")
        self.assertEqual(_resolve(_segment(("ninja", "and", [
            ("stage_changed", "within_days", {"from": [], "to": ["at_risk"], "days": 7})]))), {"fam"})
        self.assertEqual(_resolve(_segment(("ninja", "and", [
            ("stage_changed", "within_days", {"from": ["lapsed"], "to": ["at_risk"], "days": 7})]))), set())

    def test_no_new_belt_and_not_on_a_team(self):
        from events.models import Belt, NinjaBelt

        NinjaBelt.objects.create(ninja=Ninja.objects.of_guardian(self.other).get(),
                                 belt=Belt.objects.create(level=1, name="White"), awarded_on=timezone.localdate())
        self.assertEqual(_resolve(_segment(("ninja", "and", [("no_new_belt_within_days", "within_days", 365)]))), {"fam"})

        busy, idle = User.objects.create(username="busy", email="bu@example.com"), User.objects.create(username="idle", email="i@example.com")
        busy_membership = add_member(self.dojo, busy)
        add_member(self.dojo, idle)
        self._session(10).team.add(busy_membership)
        segment = _segment(("user", "and", [("account_role", "in", ["mentor"]), ("not_on_team_within_days", "within_days", 90)]))
        self.assertEqual(_resolve(segment), {"idle"})

    def test_journey_sends_once_per_cooldown_to_those_who_want_it(self):
        from .models import Journey, JourneyDelivery

        segment = _segment(("ninja", "and", [("ninja_gender", "in", [Ninja.GIRL, Ninja.BOY])]))
        journey = Journey.objects.create(name="Hello", segment=segment, category="dojo_news",
                                         template_key="campaign_girlz", cooldown_days=30)
        set_preference(self.other, MailCategory.DOJO_NEWS, False, ConsentEvent.PREFERENCES)
        with self.assertRaises(campaigns.CampaignError):  # no English template
            Journey.objects.filter(pk=journey.pk).update(template_key="nope")
            journey.refresh_from_db()
            journeys.activate(journey)
        Journey.objects.filter(pk=journey.pk).update(template_key="campaign_girlz")
        journey.refresh_from_db()
        journeys.activate(journey)

        self.assertEqual(journeys.run(), {journey.pk: 1})
        self.assertEqual(list(JourneyDelivery.objects.values_list("user__username", flat=True)), ["fam"])
        self.assertEqual(journeys.run(), {journey.pk: 0})  # within the cool-down
        JourneyDelivery.objects.update(created_at=timezone.now() - timedelta(days=31))
        self.assertEqual(journeys.run(), {journey.pk: 1})
        journeys.pause(journey)
        self.assertEqual(journeys.run(), {})

    def test_journey_pages(self):
        from accounts.models import OrganisationRole

        from .models import Journey

        admin = User.objects.create(username="orgadmin", email="ann@example.com")
        OrganisationRole.objects.create(account=admin, role=OrganisationRole.ADMIN)
        self.client.force_login(admin)
        segment = _segment(("ninja", "and", [("ninja_gender", "in", [Ninja.GIRL])]))
        response = self.client.post(reverse("manage_journey_create"), {
            "name": "We miss you", "category": "dojo_news", "template_key": "campaign_girlz",
            "segment": segment.pk, "variables": "signup_url: https://example.org", "cooldown_days": "365",
        })
        journey = Journey.objects.get()
        self.assertRedirects(response, reverse("manage_journey_detail", kwargs={"journey_id": journey.pk}))
        self.assertFalse(journey.is_active)
        page = self.client.get(reverse("manage_journey_detail", kwargs={"journey_id": journey.pk}))
        self.assertEqual(page.context["stats"]["due"], 1)
        self.client.post(reverse("manage_journey_activate", kwargs={"journey_id": journey.pk}))
        self.assertTrue(Journey.objects.get().is_active)
        self.assertEqual(self.client.get(reverse("manage_journey_list")).status_code, 200)
        self.client.force_login(self.family)
        self.assertEqual(self.client.get(reverse("manage_journey_list")).status_code, 404)


class OrganisationEventsInDigestTests(TestCase):
    def test_the_new_sessions_digest_skips_the_organisations_own_events(self):
        from .automated import announce_new_sessions

        org = make_dojo("CoderDojo Belgium", kind=Dojo.ORGANISATION)
        parent = User.objects.create(username="p", email="p@example.com")
        Guardianship.objects.create(guardian=parent, ninja=Ninja.objects.create(name="Kid", home_dojo=org))
        start = timezone.now() + timedelta(days=10)
        Event.objects.create(name="Girlz", dojo=org, status=Event.OPEN, places=10,
                             start_time=start, end_time=start + timedelta(hours=2))
        self.assertEqual(announce_new_sessions(), 0)
        self.assertFalse(EmailMessage.objects.filter(template_key="new_sessions_at_dojo").exists())

    def test_near_dojo_does_not_offer_organisation_dojos(self):
        from django.contrib.gis.geos import Point

        from .segmentation.registry import get_attribute

        make_dojo("CoderDojo Belgium", kind=Dojo.ORGANISATION, location=Point(4.35, 50.85, srid=4326))
        ghent = make_dojo("Ghent", location=Point(3.72, 51.05, srid=4326))
        self.assertEqual([c.value for c in get_attribute("near_dojo").choices()], [ghent.pk])
