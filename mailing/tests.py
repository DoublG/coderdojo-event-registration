from datetime import timedelta
from io import StringIO

from django.contrib.gis.geos import MultiPolygon, Point, Polygon
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from accounts.models import Guardianship, Ninja, User
from dojos.models import Dojo, DojoMembership
from dojos.testing import add_member, make_dojo
from events.models import Event, Registration
from geo.models import AdministrativeBoundary, Municipality

from .models import Campaign, EmailTemplate, Segment, SegmentGroup, SegmentRule
from .rendering import TemplateMissing, render
from .seed_templates import SAMPLE_CONTEXT, TEMPLATES
from .segmentation.registry import get_attributes
from .segmentation.resolver import SegmentResolver


def _family(username, *genders, **fields):
    """An adult account with one child per gender given."""
    guardian = User.objects.create(username=username, email=f"{username}@example.com", **fields)
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
        self.assertEqual(render("hello", "de", {"name": "An"})[0], "Hi An")

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
