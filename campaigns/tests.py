import re
from datetime import timedelta
from io import StringIO
from unittest.mock import patch

from django.contrib.gis.geos import MultiPolygon, Point, Polygon
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.consent import consent_fields
from accounts.models import Guardianship, Ninja, User
from campaigns import journeys
from campaigns import services as campaigns
from campaigns.models import Campaign, Segment, SegmentGroup, SegmentRule
from campaigns.segmentation.registry import get_attributes
from campaigns.segmentation.resolver import SegmentResolver
from dojos.models import Dojo, DojoMembership
from dojos.testing import add_member, make_dojo
from events.models import Event, Registration
from geo.models import AdministrativeBoundary, Municipality
from mailing.categories import MailCategory
from mailing.models import (
    ConsentEvent,
    EmailMessage,
    EmailTemplate,
)
from mailing.preferences import set_preference
from mailing.rendering import render
from mailing.seed_templates import SAMPLE_CONTEXT, TEMPLATES
from mailing.services import send
from mailing.tasks import (
    send_email_batch,
    send_pending_emails,
)
from mailing.testing import FakeConnection, make_family

Status = EmailMessage.Status


class SegmentResolverTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        make_family("girl", Ninja.GIRL)
        make_family("unlisted", Ninja.UNSPECIFIED)
        make_family("boy", Ninja.BOY)
        make_family("other", Ninja.OTHER)
        make_family("mixed", Ninja.BOY, Ninja.GIRL)
        make_family("inactive", Ninja.GIRL, is_active=False)
        make_family("no-email", Ninja.GIRL)
        User.objects.filter(username="no-email").update(email="")
        User.objects.create(username="volunteer", email="volunteer@example.com")
        User.objects.create(username="teen", email="teen@example.com", account_type=User.NINJA)

    def test_girlz_segment_selects_families_with_a_girl_or_an_unlisted_child(self):
        segment = _segment(("ninja", "and", [("ninja_gender", "in", [Ninja.GIRL, Ninja.UNSPECIFIED])]))
        self.assertEqual(_resolve(segment), {"girl", "unlisted", "mixed"})

    def test_a_child_group_only_counts_children_with_the_parents_consent(self):
        """accounts.consent: without it, a child's details never choose mail;
        rules about the account still reach the parent."""
        make_family("no-consent", Ninja.GIRL, consent=False)
        segment = _segment(("ninja", "and", [("ninja_gender", "in", [Ninja.GIRL])]))
        self.assertEqual(_resolve(segment), {"girl", "mixed"})
        segment = _segment(("user", "and", [("has_children", "is", True)]))
        self.assertIn("no-consent", _resolve(segment))

    def test_the_consent_is_per_guardian(self):
        """Two parents of one child: only the one who agreed is reached."""
        from accounts.consent import set_consent

        kid = Ninja.objects.get(name="girl-kid-0")
        co_parent = User.objects.create(username="co-parent", email="co@example.com")
        Guardianship.objects.create(guardian=co_parent, ninja=kid)
        segment = _segment(("ninja", "and", [("ninja_gender", "in", [Ninja.GIRL])]))
        self.assertNotIn("co-parent", _resolve(segment))
        set_consent(Guardianship.objects.get(guardian=co_parent), True)
        self.assertIn("co-parent", _resolve(segment))

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
        """ "A girl registered for the event" must not match a family whose
        boy is registered and whose girl isn't."""
        event = Event.objects.create(
            name="Girlz",
            dojo=make_dojo(),
            status=Event.OPEN,
            places=10,
            start_time=timezone.now() + timedelta(days=3),
            end_time=timezone.now() + timedelta(days=3, hours=2),
        )
        mixed_boy = Ninja.objects.get(name="mixed-kid-0")
        Registration.objects.create(event=event, ninja=mixed_boy, waiting_list=False, position=1)
        Registration.objects.create(
            event=event, ninja=Ninja.objects.get(name="girl-kid-0"), waiting_list=False, position=2
        )

        segment = _segment(
            (
                "ninja",
                "and",
                [
                    ("ninja_gender", "equals", Ninja.GIRL),
                    ("event", "equals", event.pk),
                ],
            )
        )
        self.assertEqual(_resolve(segment), {"girl"})

    def test_two_rules_on_the_same_relation_are_independent_subqueries(self):
        """Registered for event A *and* event B: two different
        registrations, which a single join would never match."""
        dojo = make_dojo()
        start = timezone.now() + timedelta(days=3)
        a, b = (
            Event.objects.create(
                name=n, dojo=dojo, status=Event.OPEN, places=5, start_time=start, end_time=start + timedelta(hours=2)
            )
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
        segment = _segment(
            (
                "ninja",
                "or",
                [
                    ("ninja_gender", "equals", Ninja.BOY),
                    ("ninja_gender", "equals", Ninja.OTHER),
                ],
            )
        )
        self.assertEqual(_resolve(segment), {"boy", "other", "mixed"})


class ActivityAttributeTests(TestCase):
    """ "Everyone active": volunteers whose dojo held a session in the last N
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
        kids = {
            name: Ninja.objects.of_guardian(make_family(name, Ninja.GIRL)).get()
            for name in ["came", "absent", "long-ago", "waitlisted"]
        }
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
        confirmed = Ninja.objects.of_guardian(make_family("confirmed", Ninja.BOY)).get()
        waitlisted = Ninja.objects.of_guardian(make_family("waitlisted", Ninja.BOY)).get()
        Registration.objects.create(event=unmarked, ninja=confirmed, waiting_list=False, position=1)
        Registration.objects.create(event=unmarked, ninja=waitlisted, waiting_list=True, position=2)

        self.assertEqual(self._families(365), {"confirmed"})

    def test_days_must_be_a_positive_whole_number(self):
        group = SegmentGroup.objects.create(segment=Segment.objects.create(name="x"), scope="user")
        for value in [0, -5, "365", 1.5, True]:
            with self.subTest(value=value), self.assertRaises(ValidationError):
                SegmentRule(
                    group=group, attribute="active_team_member", operator="within_days", value=value
                ).full_clean()


class LocalityAttributeTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        square = MultiPolygon(Polygon(((3.0, 50.5), (4.5, 50.5), (4.5, 51.5), (3.0, 51.5), (3.0, 50.5))), srid=4326)
        cls.east_flanders = AdministrativeBoundary.objects.create(
            kind=AdministrativeBoundary.PROVINCE,
            name="Provincie Oost-Vlaanderen",
            boundary=square,
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
        make_family("near", Ninja.BOY, postal_code="9880")
        make_family("far", Ninja.GIRL, postal_code="3500")
        User.objects.create(username="mentor-nearby", email="m@example.com", postal_code="9880")

        call_command("seed_mailing", stdout=StringIO())

        campaign = Campaign.objects.get(name="New dojo opening")
        self.assertEqual(campaign.context, {"dojo_name": "Aalter", "dojo_path": f"/dojos/{new.pk}/"})
        self.assertEqual(_resolve(campaign.segment), {"near"})

    def test_seeded_campaign_segments_resolve(self):
        dojo = make_dojo()
        session = _session(dojo, days_ago=30)
        girl_family = make_family("girl", Ninja.GIRL)
        make_family("boy", Ninja.BOY)
        Registration.objects.create(
            event=session,
            ninja=Ninja.objects.of_guardian(girl_family).get(),
            waiting_list=False,
            position=1,
            attended=True,
        )
        champion = User.objects.create(username="champion", email="c@example.com")
        add_member(dojo, champion, DojoMembership.CHAMPION)

        call_command("seed_mailing", stdout=StringIO())

        resolve = {c.name: _resolve(c.segment) for c in Campaign.objects.select_related("segment")}
        # Dojo has no location, so no new-dojo campaign here.
        self.assertEqual(resolve, {"Coolest Projects": {"girl", "champion"}, "CoderDojo Girlz": {"girl"}})


class CampaignDashboardTests(TestCase):
    def setUp(self):
        from accounts.models import OrganisationRole

        call_command("load_mail_templates", stdout=StringIO())
        self.admin = User.objects.create(username="orgadmin", first_name="Ann", email="ann@example.com")
        OrganisationRole.objects.create(account=self.admin, role=OrganisationRole.ADMIN)
        self.girl_family = make_family("girlfam", Ninja.GIRL, email="g@example.com")
        self.boy_family = make_family("boyfam", Ninja.BOY, email="b@example.com")
        for family in (self.girl_family, self.boy_family):
            set_preference(family, MailCategory.NEWSLETTER, True, ConsentEvent.SIGNUP)
        self.segment = _segment(("ninja", "and", [("ninja_gender", "in", [Ninja.GIRL])]))
        self.segment.name = "Girls"
        self.segment.save()
        self.client.force_login(self.admin)

    def _campaign(self, **fields):
        return Campaign.objects.create(
            **{
                "name": "Girlz",
                "segment": self.segment,
                "template_key": "campaign_girlz",
                "context": {"signup_url": "https://example.org"},
                **fields,
            }
        )

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

    def test_nav_links_every_role_to_the_management_area(self):
        """The board too: it asks for the Django admin there (DATA_MODEL.md §23)."""
        from accounts.models import OrganisationRole

        self.assertContains(self.client.get(reverse("account_home")), f'href="{reverse("manage_home")}"')
        board = User.objects.create(username="board", email="bo@example.com")
        OrganisationRole.objects.create(account=board, role=OrganisationRole.BOARD)
        self.client.force_login(board)
        response = self.client.get(reverse("account_home"))
        self.assertContains(response, f'href="{reverse("manage_home")}"')
        self.assertNotContains(response, 'href="/admin/"')

    # the draft

    def test_create_a_draft_with_template_variables(self):
        response = self.client.post(
            reverse("manage_campaign_create"),
            {
                "name": "Girlz spring",
                "category": "newsletter",
                "template_key": "campaign_girlz",
                "segment": self.segment.pk,
                "variables": "signup_url: https://example.org/girlz\n\n",
                "scheduled_at": "",
            },
        )
        campaign = Campaign.objects.get(name="Girlz spring")
        self.assertRedirects(response, reverse("manage_campaign_detail", kwargs={"campaign_id": campaign.pk}))
        self.assertEqual(campaign.context, {"signup_url": "https://example.org/girlz"})
        self.assertEqual(campaign.status, Campaign.Status.DRAFT)

    def test_form_only_offers_mail_people_can_switch_off_and_future_times(self):
        from campaigns.forms import CampaignForm

        form = CampaignForm()
        self.assertNotIn("service", dict(form.fields["category"].choices))
        self.assertNotIn("registration", dict(form.fields["category"].choices))
        bad = CampaignForm(
            {
                "name": "x",
                "category": "newsletter",
                "template_key": "campaign_girlz",
                "segment": self.segment.pk,
                "variables": "Bad Name: x",
                "scheduled_at": "2001-01-01T10:00",
            }
        )
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
        with patch("mailing.tasks.mail.get_connection", return_value=FakeConnection()):
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
                response = self.client.post(
                    reverse("manage_campaign_launch", kwargs={"campaign_id": campaign.pk}), follow=True
                )
                self.assertContains(response, problem)
                self.assertEqual(Campaign.objects.get(pk=campaign.pk).status, Campaign.Status.DRAFT)

    def test_launch_freezes_the_segment_and_queues_only_those_who_want_it(self):
        campaign = self._campaign()
        extra_girl_family = make_family("unsubscribed", Ninja.GIRL, email="u@example.com")  # never opted in
        self.client.post(reverse("manage_campaign_launch", kwargs={"campaign_id": campaign.pk}))
        campaign.refresh_from_db()
        self.assertEqual((campaign.status, campaign.launched_by), (Campaign.Status.QUEUED, self.admin))
        self.assertEqual(campaign.segment_snapshot["groups"][0]["rules"][0]["attribute"], "ninja_gender")

        # Editing the segment afterwards changes nothing for this campaign.
        SegmentRule.objects.filter(group__segment=self.segment).update(value=[Ninja.BOY])
        with patch("campaigns.tasks.launch_campaign.delay") as delay:
            campaigns.launch_due()
        delay.assert_called_once_with(campaign.pk, 0)
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
        response = self.client.post(
            reverse("manage_campaign_detail", kwargs={"campaign_id": campaign.pk}), {"name": "Changed"}
        )
        self.assertIsNone(response.context["form"])
        self.assertEqual(Campaign.objects.get(pk=campaign.pk).name, "Girlz")

    def test_a_scheduled_campaign_waits_for_its_time(self):
        later = timezone.now() + timedelta(hours=3)
        campaign = self._campaign(scheduled_at=later)
        campaigns.launch(campaign, self.admin)
        with patch("campaigns.tasks.launch_campaign.delay") as delay:
            campaigns.launch_due()
            delay.assert_not_called()
            campaigns.launch_due(now=later + timedelta(minutes=1))
            delay.assert_called_once_with(campaign.pk, 0)

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
        with patch("mailing.tasks.mail.get_connection", return_value=FakeConnection()) as connection:
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
        make_family("girlfam", Ninja.GIRL)
        make_family("boyfam", Ninja.BOY)
        make_family("unlisted", Ninja.UNSPECIFIED)
        self.client.post(reverse("manage_segment_create"), {"name": "Girlz", "description": "", "is_active": "on"})
        self.segment = Segment.objects.get(name="Girlz")
        self.url = reverse("manage_segment_detail", kwargs={"segment_id": self.segment.pk})

    def _add_group(self, scope, parent=None):
        self.client.post(
            reverse("manage_segment_add_group", kwargs={"segment_id": self.segment.pk}),
            {"scope": scope, **({"parent": parent.pk} if parent else {})},
        )
        return SegmentGroup.objects.filter(segment=self.segment).latest("id")

    def _add_rule(self, group, data):
        return self.client.post(
            reverse("manage_segment_add_rule", kwargs={"segment_id": self.segment.pk, "group_id": group.pk}),
            data,
            follow=True,
        )

    def test_build_a_segment_and_see_its_audience(self):
        group = self._add_group("ninja")
        response = self._add_rule(
            group, {"attribute": "ninja_gender", "operator": "in", "value": ["girl", "unspecified"]}
        )
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
        response = self.client.post(
            reverse("manage_segment_add_group", kwargs={"segment_id": self.segment.pk}),
            {"scope": "user", "parent": child.pk},
            follow=True,
        )
        self.assertContains(response, "must also be about the child")
        self.assertEqual(SegmentGroup.objects.filter(parent=child).count(), 0)

    def test_rule_fields_fit_the_attribute(self):
        group = self._add_group("ninja")
        fields_url = reverse(
            "manage_segment_rule_fields", kwargs={"segment_id": self.segment.pk, "group_id": group.pk}
        )
        gender = self.client.get(fields_url, {"attribute": "ninja_gender"})
        self.assertContains(gender, 'type="checkbox" name="value" value="girl"')
        self.assertNotContains(gender, 'value="equals"')
        days = self.client.get(fields_url, {"attribute": "attended_within_days"})
        self.assertContains(days, 'type="number" name="value"')

    def test_change_operator_remove_rule_group_and_segment(self):
        group = self._add_group("ninja")
        self._add_rule(group, {"attribute": "ninja_gender", "operator": "in", "value": ["girl"]})
        self.client.post(
            reverse("manage_segment_update_group", kwargs={"segment_id": self.segment.pk, "group_id": group.pk}),
            {"operator": "or"},
        )
        self.assertEqual(SegmentGroup.objects.get(pk=group.pk).operator, "or")
        rule = SegmentRule.objects.get()
        self.client.post(
            reverse("manage_segment_delete_rule", kwargs={"segment_id": self.segment.pk, "rule_id": rule.pk})
        )
        self.assertFalse(SegmentRule.objects.exists())
        self.client.post(
            reverse("manage_segment_delete_group", kwargs={"segment_id": self.segment.pk, "group_id": group.pk})
        )
        self.assertFalse(SegmentGroup.objects.exists())
        self.client.post(reverse("manage_segment_delete", kwargs={"segment_id": self.segment.pk}))
        self.assertFalse(Segment.objects.exists())

    def test_builder_endpoints_are_404_without_the_admin_role(self):
        group = self._add_group("ninja")
        self.client.force_login(User.objects.get(username="girlfam"))
        for url in [
            self.url,
            reverse("manage_segment_add_group", kwargs={"segment_id": self.segment.pk}),
            reverse("manage_segment_add_rule", kwargs={"segment_id": self.segment.pk, "group_id": group.pk}),
        ]:
            self.assertEqual(self.client.post(url, {"scope": "user"}).status_code, 404)


class EngagementAttributeTests(TestCase):
    """Segments on the nightly engagement snapshot (events.engagement)."""

    def setUp(self):
        from events.engagement import rebuild

        self.ghent, self.antwerp = make_dojo("Ghent"), make_dojo("Antwerp", status=Dojo.DORMANT)
        self.regular = make_family("regularfam", Ninja.GIRL)
        self.lapsed = make_family("lapsedfam", Ninja.BOY)
        regular_kid = Ninja.objects.of_guardian(self.regular).get()
        lapsed_kid = Ninja.objects.of_guardian(self.lapsed).get()
        Ninja.objects.filter(pk=lapsed_kid.pk).update(home_dojo=self.antwerp)
        for days in (150, 120, 90, 60, 30):
            Registration.objects.create(
                event=self._session(days, self.ghent), ninja=regular_kid, waiting_list=False, position=1, attended=True
            )
        for days in (330, 300, 270):
            Registration.objects.create(
                event=self._session(days, self.antwerp),
                ninja=lapsed_kid,
                waiting_list=False,
                position=1,
                attended=True,
            )
        upcoming = self._session(-7, self.ghent, status=Event.OPEN)
        Registration.objects.create(event=upcoming, ninja=regular_kid, waiting_list=False, position=1)
        rebuild()

    def _session(self, days_ago, dojo, status=Event.CLOSED):
        start = timezone.now() - timedelta(days=days_ago)
        return Event.objects.create(
            name=f"S{days_ago}",
            dojo=dojo,
            status=status,
            places=20,
            start_time=start,
            end_time=start + timedelta(hours=2),
        )

    def _one(self, attribute, operator, value):
        return _resolve(_segment(("ninja", "and", [(attribute, operator, value)])))

    def test_each_engagement_attribute(self):
        self.assertEqual(self._one("engagement_stage", "in", ["regular"]), {"regularfam"})
        self.assertEqual(self._one("engagement_stage", "in", ["lapsed"]), {"lapsedfam"})
        self.assertEqual(
            self._one("engagement_stage_at_dojo", "in", {"dojo": self.ghent.pk, "stages": ["regular"]}), {"regularfam"}
        )
        self.assertEqual(self._one("attendance_rate", "gte", 50), {"regularfam"})
        self.assertEqual(self._one("sessions_attended", "gte", 3), {"regularfam"})
        self.assertEqual(self._one("days_since_last_visit", "gte", 200), {"lapsedfam"})
        self.assertEqual(self._one("days_since_last_visit", "lte", 45), {"regularfam"})
        self.assertEqual(self._one("has_upcoming_registration", "is", True), {"regularfam"})
        self.assertEqual(self._one("main_dojo_status", "in", ["dormant"]), {"lapsedfam"})

    def test_rules_read_as_sentences_and_validate(self):
        from campaigns.segmentation.registry import get_attribute

        self.assertEqual(
            get_attribute("attendance_rate").describe("gte", 50),
            "Share of their sessions they came to (last 180 days, %) at least 50%",
        )
        self.assertEqual(
            get_attribute("engagement_stage_at_dojo").describe("in", {"dojo": self.ghent.pk, "stages": ["at_risk"]}),
            "At Ghent: At risk",
        )
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
        self.client.post(
            add,
            {
                "attribute": "engagement_stage_at_dojo",
                "operator": "in",
                "dojo": str(self.ghent.pk),
                "value": ["at_risk", "lapsed"],
            },
        )
        self.assertEqual(
            dict(SegmentRule.objects.values_list("attribute", "value")),
            {
                "missed_in_a_row": 3,
                "engagement_stage_at_dojo": {"dojo": self.ghent.pk, "stages": ["at_risk", "lapsed"]},
            },
        )


class ProfileAttributeTests(TestCase):
    """Tier 1 attributes read straight from the site's data."""

    def setUp(self):
        from events.models import Belt, NinjaBelt

        today = timezone.localdate()
        self.dojo = make_dojo("Ghent")
        self.ten = make_family("tenfam", Ninja.GIRL)
        self.fifteen = make_family("fifteenfam", Ninja.BOY)
        Ninja.objects.filter(guardianships__guardian=self.ten).update(
            date_of_birth=today.replace(year=today.year - 10), home_dojo=self.dojo
        )
        Ninja.objects.filter(guardianships__guardian=self.fifteen).update(
            date_of_birth=today.replace(year=today.year - 15)
        )
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
        event = Event.objects.create(
            name="Full",
            dojo=self.dojo,
            status=Event.OPEN,
            places=0,
            start_time=start,
            end_time=start + timedelta(hours=2),
        )
        ten_kid = Ninja.objects.of_guardian(self.ten).get()
        registration = Registration.objects.create(event=event, ninja=ten_kid, waiting_list=True, position=1)
        self.assertEqual(self._one("ninja", "waitlisted_for_event", "in", [event.pk]), {"tenfam"})

        self.client.force_login(self.ten)
        self.client.post(reverse("cancel_registration", kwargs={"registration_id": registration.pk}))
        from events.models import RegistrationCancellation

        logged = RegistrationCancellation.objects.get()
        self.assertEqual(
            (logged.ninja, logged.event, logged.was_waitlisted, logged.cancelled_by), (ten_kid, event, True, self.ten)
        )
        self.assertIsNotNone(logged.signed_up_at)
        self.assertEqual(self._one("ninja", "cancellations", "gte", 1), {"tenfam"})
        self.assertEqual(self._one("ninja", "cancellations", "lte", 0), {"fifteenfam"})


class Tier3Tests(TestCase):
    def setUp(self):
        call_command("load_mail_templates", stdout=StringIO())
        self.dojo = make_dojo("Ghent")
        self.family = make_family("fam", Ninja.GIRL)
        self.kid = Ninja.objects.of_guardian(self.family).get()
        self.other = make_family("other", Ninja.BOY)

    def _session(self, days_ago):
        start = timezone.now() - timedelta(days=days_ago)
        return Event.objects.create(
            name=f"S{days_ago}",
            dojo=self.dojo,
            status=Event.CLOSED,
            places=20,
            start_time=start,
            end_time=start + timedelta(hours=2),
        )

    def test_rebuild_records_stage_changes_once_a_day(self):
        from events.engagement import rebuild
        from events.models import NinjaEngagementChange

        for days in (170, 150, 130, 110):
            Registration.objects.create(
                event=self._session(days), ninja=self.kid, waiting_list=False, position=1, attended=True
            )
        rebuild()
        self.assertFalse(NinjaEngagementChange.objects.exists())  # the first build records nothing
        for days in (60, 40, 20):
            self._session(days)
        rebuild()
        rebuild()
        change = NinjaEngagementChange.objects.get(ninja=self.kid)
        self.assertEqual(change.to_stage, "at_risk")
        self.assertEqual(
            _resolve(
                _segment(
                    ("ninja", "and", [("stage_changed", "within_days", {"from": [], "to": ["at_risk"], "days": 7})])
                )
            ),
            {"fam"},
        )
        self.assertEqual(
            _resolve(
                _segment(
                    (
                        "ninja",
                        "and",
                        [("stage_changed", "within_days", {"from": ["lapsed"], "to": ["at_risk"], "days": 7})],
                    )
                )
            ),
            set(),
        )

    def test_no_new_belt_and_not_on_a_team(self):
        from events.models import Belt, NinjaBelt

        NinjaBelt.objects.create(
            ninja=Ninja.objects.of_guardian(self.other).get(),
            belt=Belt.objects.create(level=1, name="White"),
            awarded_on=timezone.localdate(),
        )
        self.assertEqual(
            _resolve(_segment(("ninja", "and", [("no_new_belt_within_days", "within_days", 365)]))), {"fam"}
        )

        busy, idle = (
            User.objects.create(username="busy", email="bu@example.com"),
            User.objects.create(username="idle", email="i@example.com"),
        )
        busy_membership = add_member(self.dojo, busy)
        add_member(self.dojo, idle)
        self._session(10).team.add(busy_membership)
        segment = _segment(
            ("user", "and", [("account_role", "in", ["mentor"]), ("not_on_team_within_days", "within_days", 90)])
        )
        self.assertEqual(_resolve(segment), {"idle"})

    def test_journey_sends_once_per_cooldown_to_those_who_want_it(self):
        from campaigns.models import Journey, JourneyDelivery

        segment = _segment(("ninja", "and", [("ninja_gender", "in", [Ninja.GIRL, Ninja.BOY])]))
        journey = Journey.objects.create(
            name="Hello", segment=segment, category="dojo_news", template_key="campaign_girlz", cooldown_days=30
        )
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
        from campaigns.models import Journey

        admin = User.objects.create(username="orgadmin", email="ann@example.com")
        OrganisationRole.objects.create(account=admin, role=OrganisationRole.ADMIN)
        self.client.force_login(admin)
        segment = _segment(("ninja", "and", [("ninja_gender", "in", [Ninja.GIRL])]))
        response = self.client.post(
            reverse("manage_journey_create"),
            {
                "name": "We miss you",
                "category": "dojo_news",
                "template_key": "campaign_girlz",
                "segment": segment.pk,
                "variables": "signup_url: https://example.org",
                "cooldown_days": "365",
            },
        )
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


class DojoAudienceTests(TestCase):
    """mailing.dojo_audiences: each prepared audience reaches the right
    families of that one dojo, and the child-based ones only with consent."""

    def setUp(self):
        from campaigns import dojo_audiences

        self.audiences = dojo_audiences
        self.ghent, self.antwerp = make_dojo("Ghent"), make_dojo("Antwerp")
        self.home = User.objects.create(username="home", email="home@example.com")
        self.home_kid = _kid(self.home, self.ghent, age=10)
        self.visitor = User.objects.create(username="visitor", email="visitor@example.com")
        self.visitor_kid = _kid(self.visitor, self.antwerp, age=14, consent=False)
        _place(_session(self.ghent, days_ago=20), self.visitor_kid, attended=True)
        self.elsewhere = User.objects.create(username="elsewhere", email="elsewhere@example.com")
        self.elsewhere_kid = _kid(self.elsewhere, self.antwerp, age=10)
        _place(_session(self.antwerp, days_ago=10), self.elsewhere_kid, attended=True)
        self.upcoming = _session(self.ghent, days_ago=-7, status=Event.OPEN)

    def _who(self, key, dojo=None, **params):
        definition = self.audiences.definition(key, dojo or self.ghent, params)
        return set(SegmentResolver().resolve_definition(definition).values_list("username", flat=True))

    def test_all_families_of_the_dojo_home_and_visitors(self):
        self.assertEqual(self._who("all_families"), {"home", "visitor"})
        self.assertEqual(self._who("all_families", self.antwerp), {"visitor", "elsewhere"})

    def test_booked_and_waiting_list(self):
        waiting = User.objects.create(username="waiting", email="w@example.com")
        _place(self.upcoming, self.home_kid)
        _place(self.upcoming, _kid(waiting, self.antwerp), waiting_list=True)
        self.assertEqual(self._who("session", event=self.upcoming.pk), {"home"})
        self.assertEqual(self._who("session", event=self.upcoming.pk, include_waiting_list="on"), {"home", "waiting"})
        self.assertEqual(self._who("waiting_list", event=self.upcoming.pk), {"waiting"})

    def test_came_recently(self):
        self.assertEqual(self._who("recent", days=90), {"visitor"})
        self.assertEqual(self._who("recent", days=90, dojo=self.antwerp), {"elsewhere"})

    def test_child_based_audiences_need_the_consent(self):
        self.assertEqual(self._who("age", min_age=9, max_age=11), {"home"})
        # The visitor is 14 but didn't agree: left out, and counted as such.
        self.assertEqual(self._who("age", min_age=13, max_age=15), set())
        self.assertEqual(self.audiences.reach("age", self.ghent, {"min_age": 13, "max_age": 15}), (0, 1))
        # A child of another dojo isn't one of this dojo's children.
        self.assertEqual(self._who("age", min_age=9, max_age=11, dojo=self.antwerp), {"elsewhere"})

    def test_engagement_stages_at_this_dojo(self):
        from events.models import NinjaEngagement

        today = timezone.localdate()
        NinjaEngagement.objects.create(ninja=self.home_kid, dojo=self.ghent, stage="at_risk", computed_on=today)
        NinjaEngagement.objects.create(ninja=self.elsewhere_kid, dojo=self.antwerp, stage="at_risk", computed_on=today)
        self.assertEqual(self._who("missed"), {"home"})
        self.assertEqual(self._who("new_families"), set())

    def test_pathway_only_offered_with_the_dojos_pathways(self):
        from pathways.models import Pathway

        keys = lambda: {a.key for a in self.audiences.available(self.ghent)}  # noqa: E731
        self.assertNotIn("pathway", keys())
        scratch, python = Pathway.objects.create(name="Scratch"), Pathway.objects.create(name="Python")
        self.ghent.pathways.add(scratch)
        self.assertIn("pathway", keys())
        registration = _place(_session(self.ghent, days_ago=5), self.home_kid, attended=True)
        registration.pathways.add(scratch)
        self.assertEqual(self._who("pathway", pathway=scratch.pk), {"home"})
        with self.assertRaises(self.audiences.DojoAudienceError):
            self._who("pathway", pathway=python.pk)

    def test_another_dojos_session_or_bad_values_are_refused(self):
        other = _session(self.antwerp, days_ago=-3, status=Event.OPEN)
        for key, params in [
            ("session", {"event": other.pk}),
            ("waiting_list", {"event": "nope"}),
            ("recent", {"days": 12}),
            ("age", {"min_age": 12, "max_age": 9}),
            ("age", {"min_age": 2, "max_age": 9}),
            ("nonsense", {}),
        ]:
            with self.subTest(key=key, params=params), self.assertRaises(self.audiences.DojoAudienceError):
                self.audiences.definition(key, self.ghent, params)

    def test_reach_leaves_out_who_doesnt_want_the_dojos_news(self):
        from mailing.preferences import set_dojo_mute

        self.assertEqual(self.audiences.reach("all_families", self.ghent, {}), (2, 0))
        set_dojo_mute(self.home, self.ghent, True, ConsentEvent.PREFERENCES)
        set_preference(self.visitor, MailCategory.DOJO_NEWS, False, ConsentEvent.PREFERENCES)
        self.assertEqual(self.audiences.reach("all_families", self.ghent, {}), (0, 0))

    def test_the_dojo_only_attribute_stays_out_of_the_organisations_builder(self):
        from .manage import _attributes_for

        keys = {a.key for a in _attributes_for("user")}
        self.assertIn("dojo_family", keys)
        self.assertNotIn("family_visited_dojo", keys)


class DojoMailingTests(TestCase):
    """A dojo mailing goes through the campaign pipeline with its own rules."""

    def setUp(self):
        call_command("load_mail_templates", stdout=StringIO())
        self.champion = User.objects.create(username="champ", email="champ@example.com")
        self.dojo = make_dojo("Ghent", champion=self.champion, email="ghent@example.com", languages=["nl-be", "fr-be"])
        self.nl = User.objects.create(username="nl", email="nl@example.com", preferred_language="nl-be")
        self.fr = User.objects.create(username="fr", email="fr@example.com", preferred_language="fr-be")
        self.en = User.objects.create(username="en", email="en@example.com")
        for parent in (self.nl, self.fr, self.en):
            _kid(parent, self.dojo)

    def _mailing(self, **fields):
        fields = {
            "name": "Geen sessie",
            "dojo": self.dojo,
            "category": MailCategory.DOJO_NEWS,
            "template_key": "dojo_message",
            "audience": "all_families",
            "subject": "Geen sessie zaterdag",
            "message": "Beste families, {{ site_url }} blijft letterlijk staan.",
            "created_by": self.champion,
            **fields,
        }
        campaign = Campaign.objects.create(**fields)
        campaign.set_translation("fr-be", "subject", "Pas de session samedi")
        campaign.save()
        return campaign

    def test_launch_sends_the_dojos_text_in_each_language_with_reply_to_the_dojo(self):
        campaign = self._mailing()
        self.assertEqual(campaigns.launch_problems(campaign), [])
        campaigns.launch(campaign, self.champion)
        self.assertEqual(campaign.segment_snapshot["groups"][0]["rules"][0]["attribute"], "dojo_family")
        self.assertEqual(campaigns.queue_mail(campaign.pk), 3)

        rows = {row.user.username: row for row in EmailMessage.objects.filter(campaign=campaign)}
        self.assertEqual(rows["nl"].subject, "Ghent: Geen sessie zaterdag")
        self.assertEqual(rows["fr"].subject, "Ghent : Pas de session samedi")
        # French has no message of its own, so the main language's; English isn't one of the dojo's.
        self.assertIn("Beste families", rows["fr"].body)
        self.assertEqual(rows["en"].subject, "Ghent: Geen sessie zaterdag")
        # The dojo's text is inserted, never rendered as a template.
        self.assertIn("{{ site_url }} blijft letterlijk staan", rows["nl"].body)
        self.assertEqual({(r.dojo_id, r.reply_to) for r in rows.values()}, {(self.dojo.pk, "ghent@example.com")})

        row = rows["nl"]
        EmailMessage.objects.filter(pk=row.pk).update(status=Status.SENDING, claimed_at=timezone.now())
        connection = FakeConnection()
        with (
            override_settings(DEFAULT_FROM_EMAIL="CoderDojo Belgium <noreply@example.org>"),
            patch("mailing.tasks.mail.get_connection", return_value=connection),
        ):
            send_email_batch([row.pk])
        headers = connection.sent[0].extra_headers
        self.assertEqual(headers["Reply-To"], "ghent@example.com")
        self.assertEqual(headers["From"], "Ghent via CoderDojo Belgium <noreply@example.org>")

    def test_a_family_that_muted_the_dojo_is_not_in_the_audience(self):
        from mailing.preferences import set_dojo_mute

        set_dojo_mute(self.en, self.dojo, True, ConsentEvent.PREFERENCES)
        self.assertEqual(set(campaigns.audience(self._mailing()).values_list("username", flat=True)), {"nl", "fr"})

    def test_launch_problems(self):
        self.dojo.email = ""
        self.dojo.save()
        campaign = self._mailing(subject="", audience="session", audience_params={})
        problems = " ".join(campaigns.launch_problems(campaign))
        self.assertIn("Pick one of your dojo's sessions", problems)
        self.assertIn("in Nederlands", problems)
        self.assertIn("email address", problems)

    def test_at_most_four_mailings_in_30_days(self):
        for _ in range(4):
            campaigns.launch(self._mailing(), self.champion)
        problems = campaigns.launch_problems(self._mailing())
        self.assertTrue(any("4 mails in the last 30 days" in p for p in problems))
        # A cancelled one that sent nothing gives its place back.
        cancelled = Campaign.objects.filter(dojo=self.dojo).first()
        campaigns.cancel(cancelled)
        self.assertEqual(campaigns.launch_problems(self._mailing()), [])
        # Older than 30 days doesn't count.
        Campaign.objects.filter(dojo=self.dojo).update(launched_at=timezone.now() - timedelta(days=31))
        self.assertEqual(campaigns.dojo_launches(self.dojo), 0)

    def test_test_mail_goes_to_the_author_as_the_family_would_get_it(self):
        row = campaigns.send_test(self._mailing(), self.champion)
        self.assertEqual((row.recipient, row.is_test, row.template_key), ("champ@example.com", True, "dojo_message"))
        self.assertTrue(row.subject.startswith("[Test] Ghent:"))
        self.assertEqual(Campaign.objects.get().status, Campaign.Status.DRAFT)


class DojoMailPagesTests(TestCase):
    def setUp(self):
        from dojos.testing import make_champion, make_mentor

        call_command("load_mail_templates", stdout=StringIO())
        self.champion = make_champion(username="champ", email="champ@example.com")
        self.mentor = make_mentor(username="mentor", email="mentor@example.com")
        self.dojo = make_dojo("Ghent", champion=self.champion, email="ghent@example.com")
        add_member(self.dojo, self.mentor)
        self.other = make_dojo("Antwerp", champion=make_champion(username="other"), email="a@example.com")
        self.parent = User.objects.create(username="parent", email="p@example.com")
        _kid(self.parent, self.dojo)
        self.session = _session(self.dojo, days_ago=-5, status=Event.OPEN)

    def _url(self, name, dojo=None, **kwargs):
        return reverse(name, kwargs={"dojo_id": (dojo or self.dojo).pk, **kwargs})

    def _post_new(self, **data):
        self.client.force_login(self.champion)
        fields = {"audience": "all_families", "subject": "Geen sessie", "message": "Tot volgende week!", **data}
        return self.client.post(self._url("dojo_mail_create"), fields)

    def _draft(self, **fields):
        return Campaign.objects.create(
            name="Hi",
            dojo=self.dojo,
            category=MailCategory.DOJO_NEWS,
            template_key="dojo_message",
            audience="all_families",
            subject="Hi",
            message="Hello",
            **fields,
        )

    def test_only_the_dojos_managing_team_gets_in(self):
        self.client.force_login(self.parent)
        self.assertEqual(self.client.get(self._url("dojo_mail_list")).status_code, 404)
        self.client.force_login(self.mentor)
        response = self.client.get(self._url("dojo_mail_list"))
        self.assertTemplateUsed(response, "campaigns/dojo/mail_list.html")
        self.assertContains(response, self._url("dojo_mail_list"))  # the sidebar link
        self.assertNotContains(response, self._url("dojo_mail_create"))
        self.assertEqual(self.client.get(self._url("dojo_mail_create")).status_code, 403)
        self.assertEqual(self.client.get(self._url("dojo_mail_list", dojo=self.other)).status_code, 404)

    def test_mentors_can_read_but_not_write_or_send(self):
        draft = self._draft()
        self.client.force_login(self.mentor)
        response = self.client.get(self._url("dojo_mail_detail", campaign_id=draft.pk))
        self.assertTemplateUsed(response, "campaigns/dojo/mail_detail.html")
        for name in ("dojo_mail_test", "dojo_mail_launch", "dojo_mail_cancel"):
            self.assertEqual(self.client.post(self._url(name, campaign_id=draft.pk)).status_code, 403)
        self.assertEqual(Campaign.objects.get().status, Campaign.Status.DRAFT)

    def test_the_champion_writes_a_draft(self):
        response = self._post_new(audience="session", event=self.session.pk, include_waiting_list="on")
        campaign = Campaign.objects.get()
        self.assertRedirects(response, self._url("dojo_mail_detail", campaign_id=campaign.pk))
        self.assertEqual(
            (campaign.dojo, campaign.category, campaign.template_key, campaign.created_by),
            (self.dojo, MailCategory.DOJO_NEWS, "dojo_message", self.champion),
        )
        self.assertEqual(campaign.audience_params, {"event": self.session.pk, "include_waiting_list": True})
        page = self.client.get(response.url)
        self.assertTemplateUsed(page, "campaigns/dojo/mail_form.html")
        self.assertContains(page, "Tot volgende week!")  # the preview

    def test_another_dojos_session_is_refused(self):
        theirs = _session(self.other, days_ago=-5, status=Event.OPEN)
        response = self._post_new(audience="session", event=theirs.pk)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Campaign.objects.exists())
        self.assertFalse(response.context["form"].is_valid())

    def test_the_reach_shows_a_count_never_names(self):
        self.client.force_login(self.champion)
        response = self.client.get(self._url("dojo_mail_reach"), {"audience": "all_families"})
        self.assertContains(response, "Reaches 1 family.")
        self.assertNotContains(response, "parent")
        response = self.client.get(self._url("dojo_mail_reach"), {"audience": "session"})
        self.assertContains(response, "Pick one of your dojo")

    def test_test_send_and_cancel(self):
        draft = self._draft()
        self.client.force_login(self.champion)
        self.client.post(self._url("dojo_mail_test", campaign_id=draft.pk))
        self.assertTrue(EmailMessage.objects.filter(campaign=draft, is_test=True, recipient="champ@example.com"))
        response = self.client.post(self._url("dojo_mail_launch", campaign_id=draft.pk))
        self.assertRedirects(response, self._url("dojo_mail_detail", campaign_id=draft.pk))
        draft.refresh_from_db()
        self.assertEqual((draft.status, draft.launched_by), (Campaign.Status.QUEUED, self.champion))
        detail = self.client.get(self._url("dojo_mail_detail", campaign_id=draft.pk))
        self.assertTemplateUsed(detail, "campaigns/dojo/mail_detail.html")
        self.client.post(self._url("dojo_mail_cancel", campaign_id=draft.pk))
        self.assertEqual(Campaign.objects.get().status, Campaign.Status.CANCELLED)

    def test_deleting_a_draft_and_another_dojos_mailing_is_404(self):
        theirs = Campaign.objects.create(name="x", dojo=self.other, audience="all_families")
        self.client.force_login(self.champion)
        self.assertEqual(self.client.get(self._url("dojo_mail_detail", campaign_id=theirs.pk)).status_code, 404)
        self.assertEqual(self.client.post(self._url("dojo_mail_cancel", campaign_id=theirs.pk)).status_code, 404)
        draft = self._draft()
        self.assertRedirects(
            self.client.post(self._url("dojo_mail_cancel", campaign_id=draft.pk)), self._url("dojo_mail_list")
        )
        self.assertFalse(Campaign.objects.filter(pk=draft.pk).exists())

    def test_a_launched_mailing_cant_be_edited(self):
        draft = self._draft()
        self.client.force_login(self.champion)
        self.client.post(self._url("dojo_mail_launch", campaign_id=draft.pk))
        self.client.post(
            self._url("dojo_mail_detail", campaign_id=draft.pk),
            {"audience": "all_families", "subject": "Changed", "message": "Changed"},
        )
        self.assertEqual(Campaign.objects.get().subject, "Hi")


class OrganisationSeesDojoMailTests(TestCase):
    def setUp(self):
        from accounts.models import OrganisationRole

        call_command("load_mail_templates", stdout=StringIO())
        self.admin = User.objects.create(username="orgadmin", email="ann@example.com")
        OrganisationRole.objects.create(account=self.admin, role=OrganisationRole.ADMIN)
        self.champion = User.objects.create(username="champ", email="champ@example.com")
        self.dojo = make_dojo("Ghent", champion=self.champion, email="ghent@example.com")
        self.parent = User.objects.create(username="parent", email="p@example.com")
        _kid(self.parent, self.dojo)
        self.mailing = Campaign.objects.create(
            name="Geen sessie",
            dojo=self.dojo,
            category=MailCategory.DOJO_NEWS,
            template_key="dojo_message",
            audience="all_families",
            subject="Geen sessie",
            message="Tot volgende week",
        )
        self.own = Campaign.objects.create(name="Newsletter", template_key="campaign_girlz")
        self.client.force_login(self.admin)

    def _url(self, name):
        return reverse(name, kwargs={"campaign_id": self.mailing.pk})

    def test_the_list_shows_who_sent_what_and_filters(self):
        url = reverse("manage_campaign_list")
        response = self.client.get(url)
        self.assertContains(response, "Geen sessie")
        self.assertContains(response, "All families of the dojo")
        self.assertContains(response, "Newsletter")
        only_dojos = self.client.get(url, {"from": "dojos"})
        self.assertContains(only_dojos, "Geen sessie")
        self.assertNotContains(only_dojos, ">Newsletter<")
        self.assertNotContains(self.client.get(url, {"from": "organisation"}), "Geen sessie")
        self.assertContains(self.client.get(url, {"from": str(self.dojo.pk)}), "Geen sessie")

    def test_the_organisation_never_edits_tests_or_sends_a_dojos_draft(self):
        response = self.client.get(self._url("manage_campaign_detail"))
        self.assertIsNone(response.context["form"])
        self.assertContains(response, "Tot volgende week")  # the preview
        self.client.post(self._url("manage_campaign_detail"), {"name": "Changed"})
        self.client.post(self._url("manage_campaign_test"))
        self.client.post(self._url("manage_campaign_launch"))
        self.client.post(self._url("manage_campaign_cancel"))
        self.mailing.refresh_from_db()
        self.assertEqual((self.mailing.name, self.mailing.status), ("Geen sessie", Campaign.Status.DRAFT))
        self.assertFalse(EmailMessage.objects.exists())

    def test_the_organisation_can_stop_one_going_out(self):
        campaigns.launch(self.mailing, self.champion)
        campaigns.queue_mail(self.mailing.pk)
        self.client.post(self._url("manage_campaign_cancel"))
        self.mailing.refresh_from_db()
        self.assertEqual(self.mailing.status, Campaign.Status.CANCELLED)
        self.assertEqual(EmailMessage.objects.get().status, Status.SUPPRESSED)


class DojoMailQueueTests(TestCase):
    """The dojo's own mail queue: counts per mail and reasons in words,
    never the families' addresses."""

    def setUp(self):
        from dojos.testing import make_champion, make_mentor

        call_command("load_mail_templates", stdout=StringIO())
        self.champion = make_champion(username="champ", email="champ@example.com")
        self.mentor = make_mentor(username="mentor", email="mentor@example.com")
        self.dojo = make_dojo("Ghent", champion=self.champion, email="ghent@example.com")
        add_member(self.dojo, self.mentor)
        self.other = make_dojo("Antwerp")
        self.families = []
        for name in ("anna", "bert", "carl"):
            parent = User.objects.create(username=name, email=f"{name}@families.example")
            _kid(parent, self.dojo)
            self.families.append(parent)
        self.url = reverse("dojo_mail_queue", kwargs={"dojo_id": self.dojo.pk})

    def _mailing(self):
        campaign = Campaign.objects.create(
            name="Hi",
            dojo=self.dojo,
            category=MailCategory.DOJO_NEWS,
            template_key="dojo_message",
            audience="all_families",
            subject="Geen sessie",
            message="Tot volgende week",
        )
        campaigns.launch(campaign, self.champion)
        return campaign

    def test_counts_per_mail_and_reasons_without_addresses(self):
        from mailing.preferences import set_dojo_mute

        anna, bert, carl = self.families
        set_dojo_mute(carl, self.dojo, True, ConsentEvent.PREFERENCES)
        campaign = self._mailing()
        # Carl muted the dojo, so the audience leaves him out; queue him by hand as a held-back row.
        send(
            carl,
            MailCategory.DOJO_NEWS,
            "dojo_message",
            campaigns.dojo_context(campaign, carl),
            dojo=self.dojo,
            campaign=campaign,
        )
        campaigns.queue_mail(campaign.pk)
        EmailMessage.objects.filter(user=anna).update(status=Status.SENT, sent_at=timezone.now())
        EmailMessage.objects.filter(user=bert).update(
            status=Status.BOUNCED, status_reason="Bounced 5.1.1 bert@families.example"
        )
        # Another dojo's mail and the organisation's never show.
        EmailMessage.objects.create(
            user=anna, category=MailCategory.DOJO_NEWS, subject="Antwerp news", body="", dojo=self.other
        )
        EmailMessage.objects.create(user=anna, category=MailCategory.NEWSLETTER, subject="Newsletter", body="")

        self.client.force_login(self.mentor)  # any role can read it
        response = self.client.get(self.url)
        self.assertTemplateUsed(response, "campaigns/dojo/mail_queue.html")
        self.assertEqual(
            response.context["counts"], {"waiting": 0, "sent_today": 1, "not_delivered": 1, "held_back": 1}
        )
        [row] = response.context["rows"]
        self.assertEqual((row["label"], row["sent"], row["not_delivered"], row["held_back"]), ("Geen sessie", 1, 1, 1))
        self.assertEqual(response.context["held_back"], [("The family stopped your dojo's news.", 1)])
        for family in self.families:
            self.assertNotContains(response, family.email)
        self.assertNotContains(response, "Antwerp news")
        self.assertNotContains(response, "Newsletter")

    def test_the_automatic_mail_and_tests_have_their_own_rows(self):
        from mailing.automated import announce_new_sessions

        _session(self.dojo, days_ago=-10, status=Event.OPEN)
        announce_new_sessions()
        draft = Campaign.objects.create(
            name="Draft",
            dojo=self.dojo,
            category=MailCategory.DOJO_NEWS,
            template_key="dojo_message",
            audience="all_families",
            subject="Draft",
            message="Hello",
        )
        campaigns.send_test(draft, self.champion)
        self.client.force_login(self.champion)
        labels = {row["label"]: row["waiting"] for row in self.client.get(self.url).context["rows"]}
        self.assertEqual(labels, {"New sessions (the automatic mail)": 3, "Tests sent to yourself": 1})

    def test_stalled_mail_shows_a_warning(self):
        row = EmailMessage.objects.create(
            user=self.families[0], category=MailCategory.DOJO_NEWS, subject="x", body="", dojo=self.dojo
        )
        EmailMessage.objects.filter(pk=row.pk).update(created_at=timezone.now() - timedelta(hours=2))
        self.client.force_login(self.champion)
        self.assertContains(self.client.get(self.url), "Mail isn't going out.")

    def test_only_the_dojos_team(self):
        self.client.force_login(self.families[0])
        self.assertEqual(self.client.get(self.url).status_code, 404)
        self.client.force_login(self.champion)
        other = reverse("dojo_mail_queue", kwargs={"dojo_id": self.other.pk})
        self.assertEqual(self.client.get(other).status_code, 404)
        self.assertContains(self.client.get(reverse("dojo_mail_list", kwargs={"dojo_id": self.dojo.pk})), self.url)


class DojoTeamMailTests(TestCase):
    """A champion's mail to the dojo's own team: volunteer mail to its
    active champion and mentors, outside the limit on mail to families."""

    def setUp(self):
        from dojos.testing import make_champion, make_mentor

        call_command("load_mail_templates", stdout=StringIO())
        self.champion = make_champion(username="champ", email="champ@example.com")
        self.mentor = make_mentor(username="mentor", email="mentor@example.com")
        self.dojo = make_dojo("Ghent", champion=self.champion, email="ghent@example.com")
        add_member(self.dojo, self.mentor)
        add_member(
            self.dojo, make_mentor(username="asked", email="asked@example.com"), status=DojoMembership.REQUESTED
        )
        add_member(self.dojo, make_mentor(username="gone", email="gone@example.com"), status=DojoMembership.DORMANT)
        teen = User.objects.create(username="teen", email="teen@example.com", account_type=User.NINJA)
        add_member(self.dojo, teen, DojoMembership.YOUTH_MENTOR)
        other = make_dojo("Antwerp")
        add_member(other, make_mentor(username="elsewhere", email="e@example.com"))
        self.parent = User.objects.create(username="parent", email="p@example.com")
        _kid(self.parent, self.dojo)

    def _team_mailing(self):
        from campaigns.dojo_audiences import TEAM_TEMPLATE

        return Campaign.objects.create(
            name="Planning",
            dojo=self.dojo,
            category=MailCategory.VOLUNTEER,
            template_key=TEAM_TEMPLATE,
            audience="team",
            subject="Planning",
            message="Who can help on Saturday?",
        )

    def test_the_team_is_the_active_champion_and_mentors(self):
        from campaigns import dojo_audiences

        definition = dojo_audiences.definition("team", self.dojo, {})
        who = set(SegmentResolver().resolve_definition(definition).values_list("username", flat=True))
        self.assertEqual(who, {"champ", "mentor"})
        set_preference(self.mentor, MailCategory.VOLUNTEER, False, ConsentEvent.PREFERENCES)
        self.assertEqual(dojo_audiences.reach("team", self.dojo, {}), (1, 0))

    def test_writing_to_the_team_through_the_form(self):
        self.client.force_login(self.champion)
        self.client.post(
            reverse("dojo_mail_create", kwargs={"dojo_id": self.dojo.pk}),
            {"audience": "team", "subject": "Planning", "message": "Who can help?"},
        )
        campaign = Campaign.objects.get()
        self.assertEqual((campaign.category, campaign.template_key), (MailCategory.VOLUNTEER, "dojo_team_message"))
        response = self.client.get(reverse("dojo_mail_reach", kwargs={"dojo_id": self.dojo.pk}), {"audience": "team"})
        self.assertContains(response, "Reaches 2 team members.")

    def test_team_mail_goes_out_as_volunteer_mail_and_a_mute_doesnt_stop_it(self):
        from mailing.preferences import set_dojo_mute
        from mailing.services import read_unsubscribe_token

        set_dojo_mute(self.mentor, self.dojo, True, ConsentEvent.PREFERENCES)
        campaign = self._team_mailing()
        self.assertEqual(campaigns.launch_problems(campaign), [])
        campaigns.launch(campaign, self.champion)
        self.assertEqual(campaigns.queue_mail(campaign.pk), 2)
        row = EmailMessage.objects.get(user=self.mentor)
        self.assertEqual(
            (row.category, row.status, row.reply_to), (MailCategory.VOLUNTEER, Status.PENDING, "ghent@example.com")
        )
        self.assertTrue(row.subject.startswith("Ghent team: Planning"))
        self.assertIn("because you're on the dojo's team", row.body)
        # Its unsubscribe link is about volunteering mail, not this dojo's news.
        token = re.search(r"/mail/unsubscribe/([^/]+)/", row.body).group(1)
        self.assertEqual(read_unsubscribe_token(token), (self.mentor.pk, MailCategory.VOLUNTEER, None))

    def test_team_mail_doesnt_count_towards_the_limit_on_mail_to_families(self):
        for _ in range(5):
            campaigns.launch(self._team_mailing(), self.champion)
        self.assertEqual(campaigns.dojo_launches(self.dojo), 0)

    def test_a_mismatched_kind_of_mail_is_refused(self):
        campaign = self._team_mailing()
        campaign.category = MailCategory.DOJO_NEWS
        self.assertIn(
            "A dojo's mail is news for its families, or mail for its team.", campaigns.launch_problems(campaign)
        )


@override_settings(MAILING_CAMPAIGN_CHUNK_SIZE=2)
class CampaignChunkTests(TestCase):
    """mailing.campaigns.queue_chunk and the launch_campaign task: a campaign
    is queued a chunk at a time, each chunk queueing the next behind what's
    waiting, so mail queued meanwhile never waits for the whole campaign
    (CAPACITY.md, finding 8)."""

    def setUp(self):
        call_command("load_mail_templates", stdout=StringIO())
        self.admin = User.objects.create(username="orgadmin", email="ann@example.com")
        self.families = [make_family(f"fam{n}", Ninja.GIRL) for n in range(5)]
        for family in self.families:
            set_preference(family, MailCategory.NEWSLETTER, True, ConsentEvent.SIGNUP)
        self.campaign = Campaign.objects.create(
            name="Girlz",
            segment=_segment(("ninja", "and", [("ninja_gender", "in", [Ninja.GIRL])])),
            template_key="campaign_girlz",
            context={"signup_url": "https://example.org"},
        )
        campaigns.launch(self.campaign, self.admin)

    def _run(self, *args):
        """Run one launch_campaign task; returns (queued, the next task's args or None)."""
        from .tasks import launch_campaign

        with patch("campaigns.tasks.launch_campaign.delay") as delay:
            queued = launch_campaign(*args)
        return queued, (delay.call_args.args if delay.called else None)

    def test_each_task_queues_one_chunk_and_queues_the_next(self):
        queued, following = self._run(self.campaign.pk)
        self.assertEqual(queued, 2)
        tasks = 1
        while following:
            more, following = self._run(*following)
            queued += more
            tasks += 1
        self.assertEqual((queued, tasks), (5, 3))
        self.assertEqual(EmailMessage.objects.filter(campaign=self.campaign).count(), 5)
        self.campaign.refresh_from_db()
        self.assertIsNotNone(self.campaign.queued_at)
        self.assertEqual(self.campaign.queued_up_to, max(family.pk for family in self.families))

    def test_a_second_chain_stops_and_a_stalled_one_is_resumed_where_it_got(self):
        _queued, following = self._run(self.campaign.pk)
        # The same task again (a duplicate): the cursor moved, so it stops.
        self.assertEqual(self._run(self.campaign.pk, 0), (0, None))
        # The worker died before the next chunk: the beat resumes from the cursor.
        with patch("campaigns.tasks.launch_campaign.delay") as delay:
            campaigns.launch_due()
        delay.assert_called_once_with(*following)
        self.assertEqual(campaigns.queue_mail(self.campaign.pk), 3)
        self.assertEqual(EmailMessage.objects.filter(campaign=self.campaign).count(), 5)

    def test_cancelling_between_chunks_queues_nothing_more(self):
        _queued, following = self._run(self.campaign.pk)
        campaigns.cancel(Campaign.objects.get(pk=self.campaign.pk))
        self.assertEqual(self._run(*following), (0, None))
        rows = EmailMessage.objects.filter(campaign=self.campaign)
        self.assertEqual((rows.count(), set(rows.values_list("status", flat=True))), (2, {Status.SUPPRESSED}))

    def test_booking_mail_goes_out_between_two_chunks(self):
        """The mailing worker takes tasks first in, first out: a booking
        confirmation queued during a launch waits for one chunk, not for
        the whole campaign."""
        from unittest.mock import Mock

        from .tasks import launch_campaign

        queue = [("chunk", (self.campaign.pk,))]

        def dispatch(signatures):
            return Mock(apply_async=lambda: queue.extend(("batch", s.args) for s in signatures))

        parent = User.objects.create(username="booker", email="booker@example.com")
        with (
            patch("campaigns.tasks.launch_campaign.delay", side_effect=lambda *a: queue.append(("chunk", a))),
            patch("mailing.tasks.group", side_effect=dispatch),
            patch("mailing.tasks.mail.get_connection", return_value=FakeConnection()),
        ):
            launch_campaign(*queue.pop(0)[1])  # the first chunk
            booking = send(
                parent,
                MailCategory.REGISTRATION,
                "registration_confirmed",
                SAMPLE_CONTEXT["registration_confirmed"],
            )
            send_pending_emails()  # the dispatcher, every 10 seconds
            order = []
            while queue:
                kind, args = queue.pop(0)
                if kind == "chunk":
                    launch_campaign(*args)
                else:
                    send_email_batch(*args)
                    if EmailMessage.objects.get(pk=booking.pk).status == Status.SENT and "booking" not in order:
                        order.append("booking")
                order.append(kind)
        # One chunk ran before the booking's batch, the last one after it.
        self.assertEqual(order[:3], ["chunk", "booking", "batch"])
        self.assertIn("chunk", order[3:])
        self.assertIsNotNone(Campaign.objects.get(pk=self.campaign.pk).queued_at)


def _resolve(segment):
    return set(SegmentResolver().resolve(segment).values_list("username", flat=True))


def _segment(*groups):
    """groups: (scope, operator, [(attribute, operator, value), ...])"""
    segment = Segment.objects.create(name="Test")
    for scope, operator, rules in groups:
        group = SegmentGroup.objects.create(segment=segment, scope=scope, operator=operator)
        for attribute, rule_operator, value in rules:
            SegmentRule.objects.create(group=group, attribute=attribute, operator=rule_operator, value=value)
    return segment


def _session(dojo, days_ago, status=Event.CLOSED):
    start = timezone.now() - timedelta(days=days_ago)
    return Event.objects.create(
        name=f"Session {days_ago}",
        dojo=dojo,
        status=status,
        places=20,
        start_time=start,
        end_time=start + timedelta(hours=2),
    )


def _kid(guardian, dojo=None, age=10, consent=True, name="kid"):
    today = timezone.localdate()
    ninja = Ninja.objects.create(
        name=f"{guardian.username}-{name}", home_dojo=dojo, date_of_birth=today.replace(year=today.year - age)
    )
    Guardianship.objects.create(guardian=guardian, ninja=ninja, **consent_fields(consent))
    return ninja


def _place(event, ninja, waiting_list=False, attended=None):
    return Registration.objects.create(
        event=event, ninja=ninja, waiting_list=waiting_list, position=1, attended=attended
    )
