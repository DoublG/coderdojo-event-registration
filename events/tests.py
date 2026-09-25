from datetime import timedelta

from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import Guardianship, Ninja, User
from dojos.models import Dojo
from dojos.testing import make_dojo

from .engagement import is_aimed_at
from .models import Event, Registration


def _future_event(dojo, **kwargs):
    now = timezone.now()
    defaults = {
        "name": "Session",
        "dojo": dojo,
        "status": Event.OPEN,
        "start_time": now + timedelta(days=7),
        "end_time": now + timedelta(days=7, hours=2),
        "places": 10,
    }
    defaults.update(kwargs)
    return Event.objects.create(**defaults)


class EventListViewTests(TestCase):
    def test_renders_upcoming_events(self):
        dojo = make_dojo("Ghent")
        _future_event(dojo)
        response = self.client.get(reverse("event_list"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "events/event_list.html")
        self.assertEqual(len(response.context["events"]), 1)

    def test_htmx_request_returns_partial_template(self):
        response = self.client.get(reverse("event_list"), HTTP_HX_REQUEST="true")
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "events/partials/_event_results_page.html")

    def test_filters_by_dojo(self):
        ghent = make_dojo("Ghent")
        antwerp = make_dojo("Antwerp")
        ghent_event = _future_event(ghent)
        _future_event(antwerp)

        response = self.client.get(reverse("event_list"), {"dojo": ghent.id})

        self.assertEqual(list(response.context["events"]), [ghent_event])

    def test_draft_event_is_hidden(self):
        dojo = make_dojo("Ghent")
        _future_event(dojo, status=Event.DRAFT)
        response = self.client.get(reverse("event_list"))
        self.assertEqual(len(response.context["events"]), 0)

    def test_closed_event_still_shown(self):
        dojo = make_dojo("Ghent")
        event = _future_event(dojo, status=Event.CLOSED)
        response = self.client.get(reverse("event_list"))
        self.assertEqual(list(response.context["events"]), [event])


class UpcomingSessionsWidgetViewTests(TestCase):
    def test_renders_partial(self):
        cache.clear()  # upcoming_available_events() is cached (events/search.py)
        dojo = make_dojo("Ghent")
        _future_event(dojo)
        response = self.client.get(reverse("upcoming_sessions_widget"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "events/partials/_upcoming_sessions_page.html")


class EventDetailViewTests(TestCase):
    def test_existing_event_renders(self):
        dojo = make_dojo("Ghent")
        event = _future_event(dojo)
        response = self.client.get(reverse("event_detail", kwargs={"event_id": event.id}))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["event"], event)

    def test_missing_event_is_404(self):
        response = self.client.get(reverse("event_detail", kwargs={"event_id": 999999}))
        self.assertEqual(response.status_code, 404)

    def test_draft_event_is_404(self):
        dojo = make_dojo("Ghent")
        event = _future_event(dojo, status=Event.DRAFT)
        response = self.client.get(reverse("event_detail", kwargs={"event_id": event.id}))
        self.assertEqual(response.status_code, 404)


class GirlsSessionLabelTests(TestCase):
    """Event.audience = girls is a label on the public pages; it never
    restricts who can sign up."""

    @classmethod
    def setUpTestData(cls):
        cls.dojo = make_dojo("Ghent")
        cls.girls = _future_event(cls.dojo, name="Girlz", audience=Event.GIRLS)
        cls.everyone = _future_event(cls.dojo, name="Everyone", start_time=timezone.now() + timedelta(days=8),
                                     end_time=timezone.now() + timedelta(days=8, hours=2))

    def test_label_on_event_detail_only_for_girls_sessions(self):
        self.assertContains(self.client.get(reverse("event_detail", kwargs={"event_id": self.girls.id})), "Girls' session")
        self.assertNotContains(self.client.get(reverse("event_detail", kwargs={"event_id": self.everyone.id})), "Girls' session")

    def test_label_on_event_list(self):
        self.assertContains(self.client.get(reverse("event_list")), "Girls' session", count=1)

    def test_a_boy_can_sign_up_for_a_girls_session(self):
        guardian = User.objects.create(username="g1", email="g1@example.com")
        boy = Ninja.objects.create(name="Boy", gender=Ninja.BOY)
        Guardianship.objects.create(guardian=guardian, ninja=boy)
        self.client.force_login(guardian)

        self.client.post(reverse("event_signup", kwargs={"event_id": self.girls.id}),
                         {"child": [str(boy.id)], "child_order": str(boy.id)})

        self.assertTrue(Registration.objects.filter(event=self.girls, ninja=boy, waiting_list=False).exists())


class EventSignupViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.dojo = make_dojo("Ghent")
        cls.guardian = User.objects.create(username="g1", email="g1@example.com")
        cls.child = Ninja.objects.create(name="Kid One")
        Guardianship.objects.create(guardian=cls.guardian, ninja=cls.child)

    def test_login_required(self):
        event = _future_event(self.dojo)
        response = self.client.get(reverse("event_signup", kwargs={"event_id": event.id}))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response.url)

    def test_signup_confirms_when_places_available(self):
        event = _future_event(self.dojo, places=10)
        self.client.force_login(self.guardian)

        response = self.client.post(
            reverse("event_signup", kwargs={"event_id": event.id}),
            {"child": [str(self.child.id)], "child_order": str(self.child.id)},
        )

        self.assertEqual(response.status_code, 200)
        registration = Registration.objects.get(event=event, ninja=self.child)
        self.assertFalse(registration.waiting_list)
        self.assertEqual(response.context["results"][0]["waiting_list"], False)

    def test_cannot_sign_up_another_familys_ninja(self):
        """Only ninjas the account is a guardian of can be signed up — a
        foreign child id in the POST is silently ignored."""
        other_parent = User.objects.create(username="g2", email="g2@example.com")
        event = _future_event(self.dojo, places=10)
        self.client.force_login(other_parent)

        response = self.client.post(
            reverse("event_signup", kwargs={"event_id": event.id}),
            {"child": [str(self.child.id)], "child_order": str(self.child.id)},
        )

        self.assertEqual(response.context["error"], "Please select at least one child.")
        self.assertFalse(Registration.objects.filter(event=event).exists())

    def test_ninja_login_signs_up_only_itself(self):
        """A child with their own login (DATA_MODEL.md §17) signs themselves
        up; another ninja's id in the post is ignored."""
        ninja_login = User.objects.create(username="kid", account_type=User.NINJA)
        self.child.account = ninja_login
        self.child.save(update_fields=["account"])
        sibling = Ninja.objects.create(name="Sibling")
        Guardianship.objects.create(guardian=self.guardian, ninja=sibling)
        event = _future_event(self.dojo, places=10)
        self.client.force_login(ninja_login)

        response = self.client.post(
            reverse("event_signup", kwargs={"event_id": event.id}),
            {"child": [str(self.child.id), str(sibling.id)], "child_order": f"{self.child.id},{sibling.id}"},
        )

        self.assertEqual([entry["child"] for entry in response.context["children"]], [self.child])
        self.assertEqual(list(Registration.objects.filter(event=event).values_list("ninja", flat=True)), [self.child.id])

    def test_signup_waitlists_when_full(self):
        event = _future_event(self.dojo, places=0)
        self.client.force_login(self.guardian)

        self.client.post(
            reverse("event_signup", kwargs={"event_id": event.id}),
            {"child": [str(self.child.id)], "child_order": str(self.child.id)},
        )

        registration = Registration.objects.get(event=event, ninja=self.child)
        self.assertTrue(registration.waiting_list)

    def test_signup_with_no_children_selected_shows_error(self):
        event = _future_event(self.dojo)
        self.client.force_login(self.guardian)

        response = self.client.post(reverse("event_signup", kwargs={"event_id": event.id}), {})

        self.assertIsNotNone(response.context["error"])
        self.assertEqual(Registration.objects.count(), 0)

    def test_already_registered_child_cannot_double_signup(self):
        event = _future_event(self.dojo)
        Registration.objects.create(event=event, ninja=self.child, waiting_list=False, position=1)
        self.client.force_login(self.guardian)

        response = self.client.post(
            reverse("event_signup", kwargs={"event_id": event.id}),
            {"child": [str(self.child.id)], "child_order": str(self.child.id)},
        )

        self.assertIsNotNone(response.context["error"])
        self.assertEqual(Registration.objects.filter(event=event, ninja=self.child).count(), 1)

    def test_closed_event_blocks_signup(self):
        event = _future_event(self.dojo, status=Event.CLOSED)
        self.client.force_login(self.guardian)

        response = self.client.post(
            reverse("event_signup", kwargs={"event_id": event.id}),
            {"child": [str(self.child.id)], "child_order": str(self.child.id)},
        )

        self.assertIsNotNone(response.context["error"])
        self.assertEqual(Registration.objects.count(), 0)

    def test_draft_event_signup_is_404(self):
        event = _future_event(self.dojo, status=Event.DRAFT)
        self.client.force_login(self.guardian)
        response = self.client.get(reverse("event_signup", kwargs={"event_id": event.id}))
        self.assertEqual(response.status_code, 404)


class BeltAndBadgeTests(TestCase):
    """events.awards: belts are an append-only history awarded by a dojo's
    active champion/mentors; milestone badges follow sessions attended."""

    def setUp(self):
        from dojos.testing import add_member, make_champion, make_mentor

        from .models import Badge, Belt

        self.Badge = Badge
        self.white = Belt.objects.create(level=1, name="White belt")
        self.yellow = Belt.objects.create(level=2, name="Yellow belt")
        self.champion_user = make_champion(username="champ", first_name="Jan")
        self.dojo = make_dojo("Ghent", champion=self.champion_user)
        self.champion = self.dojo.champion_membership
        self.mentor = add_member(self.dojo, make_mentor(username="mentor"))
        self.ninja = Ninja.objects.create(name="Mila")
        self.event = _future_event(self.dojo)
        self.registration = Registration.objects.create(event=self.event, ninja=self.ninja, waiting_list=False, position=1)

    def test_award_records_who_and_in_which_role(self):
        from .awards import award_belt

        award = award_belt(self.ninja, self.white, self.mentor, note=" Finished a game ")

        self.assertEqual(award.awarded_by, self.mentor.user)
        self.assertEqual(award.awarded_as_membership, self.mentor)
        self.assertEqual(award.awarded_as_role, "mentor")
        self.assertEqual(award.note, "Finished a game")
        self.assertEqual(self.ninja.current_belt, self.white)
        self.assertIn("as mentor of Ghent", award.awarded_by_label)

    def test_current_belt_is_the_highest_and_history_is_kept(self):
        from .awards import award_belt

        award_belt(self.ninja, self.white, self.champion)
        award_belt(self.ninja, self.yellow, self.champion)

        self.assertEqual(self.ninja.current_belt, self.yellow)
        self.assertEqual(self.ninja.belts.count(), 2)

    def test_cannot_award_a_belt_at_or_below_the_current_one(self):
        from .awards import BeltError, award_belt

        award_belt(self.ninja, self.yellow, self.champion)
        with self.assertRaises(BeltError):
            award_belt(self.ninja, self.white, self.champion)
        with self.assertRaises(BeltError):
            award_belt(self.ninja, self.yellow, self.champion)

    def test_only_active_managers_with_a_valid_check_can_award(self):
        from dojos.models import DojoMembership
        from dojos.testing import add_member, make_mentor

        from .awards import BeltError, award_belt

        dormant = add_member(self.dojo, make_mentor(username="gone"), status=DojoMembership.DORMANT)
        lapsed_user = make_mentor(username="lapsed")
        lapsed = add_member(self.dojo, lapsed_user)
        lapsed_user.background_check_expires_at = timezone.now() - timedelta(days=1)
        lapsed_user.save()
        for membership in (dormant, lapsed):
            with self.assertRaises(BeltError):
                award_belt(self.ninja, self.white, membership)
        self.assertFalse(self.ninja.belts.exists())

    def test_ninja_must_have_been_to_the_dojo(self):
        from dojos.testing import make_champion

        from .awards import BeltError, award_belt

        other = make_dojo("Antwerp", champion=make_champion(username="other"))
        with self.assertRaises(BeltError):
            award_belt(self.ninja, self.white, other.champion_membership)

    def test_milestones_follow_attendance_and_can_grant_a_belt(self):
        from .awards import sync_milestones

        first = self.Badge.objects.create(name="White Band", kind=self.Badge.MILESTONE, threshold=1, grants_belt=self.white)
        second = self.Badge.objects.create(name="Green Band", kind=self.Badge.MILESTONE, threshold=2)

        sync_milestones(self.ninja, self.mentor)
        self.assertIsNone(self.ninja.badges.get(badge=first).earned_date)
        self.assertFalse(self.ninja.badges.filter(badge=second).exists())

        self.registration.attended = True
        self.registration.save()
        sync_milestones(self.ninja, self.mentor)

        self.assertIsNotNone(self.ninja.badges.get(badge=first).earned_date)
        progress = self.ninja.badges.get(badge=second)
        self.assertEqual((progress.progress_current, progress.progress_total, progress.earned_date), (1, 2, None))
        belt = self.ninja.belts.get()
        self.assertEqual((belt.belt, belt.awarded_as_membership), (self.white, self.mentor))

        # Unmarking never takes an earned badge (or belt) away.
        self.registration.attended = None
        self.registration.save()
        sync_milestones(self.ninja, self.mentor)
        self.assertIsNotNone(self.ninja.badges.get(badge=first).earned_date)
        self.assertEqual(self.ninja.belts.count(), 1)

    def test_milestone_needs_a_threshold(self):
        from django.core.exceptions import ValidationError

        with self.assertRaises(ValidationError):
            self.Badge(name="Broken", kind=self.Badge.MILESTONE).full_clean()
        with self.assertRaises(ValidationError):
            self.Badge(name="One-off", kind=self.Badge.ONE_OFF, threshold=3).full_clean()


class StrNeverQueriesTests(TestCase):
    """__str__ can run where the database can't be hit (under ASGI): the
    default managers preload the dojo and municipality it reads."""

    def setUp(self):
        from django.contrib.gis.geos import Point

        from geo.models import Municipality

        self.municipality = Municipality.objects.create(postal_code="9000", name="Gent", center=Point(3.72, 51.05, srid=4326))
        self.dojo = make_dojo("Ghent", municipality=self.municipality)
        self.event = Event.objects.create(
            name="Session", dojo=self.dojo, start_time=timezone.now(), end_time=timezone.now() + timedelta(hours=2), places=5,
        )

    def test_default_manager_preloads_dojo_and_municipality(self):
        event = Event.objects.get(pk=self.event.pk)
        with self.assertNumQueries(0):
            self.assertEqual(str(event), "Session (Ghent (9000 Gent))")
            self.assertEqual(str(event.dojo), "Ghent (9000 Gent)")



class EngagementTests(TestCase):
    """events.engagement: stages measured against the sessions meant for
    each child (DATA_MODEL.md §11, "Engagement snapshot")."""

    def setUp(self):
        self.dojo = make_dojo("Ghent")
        self.ninja = Ninja.objects.create(name="Emma", gender=Ninja.GIRL, date_of_birth=timezone.localdate() - timedelta(days=11 * 365))

    def _session(self, days_ago, dojo=None, **fields):
        start = timezone.now() - timedelta(days=days_ago)
        return Event.objects.create(name=f"S{days_ago}", dojo=dojo or self.dojo, status=Event.CLOSED, places=20,
                                    start_time=start, end_time=start + timedelta(hours=2), **fields)

    def _came(self, event, ninja=None, attended=True):
        Registration.objects.create(event=event, ninja=ninja or self.ninja, waiting_list=False, position=1, attended=attended)

    def _overall(self, ninja=None):
        from .engagement import rebuild
        from .models import NinjaEngagement

        rebuild()
        return NinjaEngagement.objects.get(ninja=ninja or self.ninja, dojo=None)

    def test_regular_at_a_monthly_dojo(self):
        for days in (150, 120, 90, 60, 30):
            session = self._session(days)
            self._came(session)
        row = self._overall()
        self.assertEqual((row.stage, row.attended_180d, row.offered_180d), ("regular", 5, 5))
        self.assertEqual(row.main_dojo, self.dojo)

    def test_at_risk_after_three_missed_sessions(self):
        for days in (170, 150, 130, 110):
            self._came(self._session(days))
        for days in (60, 40, 20):
            self._session(days)
        row = self._overall()
        self.assertEqual((row.stage, row.missed_in_a_row), ("at_risk", 3))

    def test_lapsed_never_new_and_aged_out(self):
        lapsed = Ninja.objects.create(name="Old visitor")
        for days in (300, 280, 260):
            self._came(self._session(days), ninja=lapsed)
        never = Ninja.objects.create(name="Never")
        new = Ninja.objects.create(name="New")
        self._came(self._session(20), ninja=new)
        adult = Ninja.objects.create(name="Adult", date_of_birth=timezone.localdate() - timedelta(days=19 * 365))
        self._came(self._session(25), ninja=adult)
        stages = {n.name: self._overall(n).stage for n in (lapsed, never, new, adult)}
        self.assertEqual(stages, {"Old visitor": "lapsed", "Never": "never_attended", "New": "new", "Adult": "aged_out"})

    def test_a_session_nobody_marked_counts_a_confirmed_place(self):
        unmarked = self._session(30)
        Registration.objects.create(event=unmarked, ninja=self.ninja, waiting_list=False, position=1)
        row = self._overall()
        self.assertEqual(row.attended_180d, 1)
        self.assertFalse(row.from_marked_attendance)

    def test_a_boy_does_not_miss_a_girls_session_or_one_for_older_children(self):
        boy = Ninja.objects.create(name="Liam", gender=Ninja.BOY, date_of_birth=timezone.localdate() - timedelta(days=8 * 365))
        for days in (170, 150, 130):
            self._came(self._session(days), ninja=boy)
        self._session(60, audience=Event.GIRLS)
        self._session(40, min_age=12)
        self._session(20, audience=Event.GIRLS)
        row = self._overall(boy)
        self.assertEqual((row.missed_in_a_row, row.offered_180d), (0, 3))
        self.assertFalse(is_aimed_at(boy, Event(audience=Event.GIRLS, start_time=timezone.now())))

    def test_overall_counts_a_visit_at_another_dojo(self):
        elsewhere = make_dojo("Antwerp")
        self.ninja.home_dojo = self.dojo
        self.ninja.save()
        for days in (60, 40):
            self._session(days)
        self._came(self._session(20, dojo=elsewhere))
        row = self._overall()
        self.assertEqual((row.attended_180d, row.missed_in_a_row), (1, 0))
        self.assertEqual(row.stage, "new")

    def test_upcoming_booking_and_rebuild_replaces_rows(self):
        from .engagement import rebuild
        from .models import NinjaEngagement

        future = _future_event(self.dojo)
        Registration.objects.create(event=future, ninja=self.ninja, waiting_list=False, position=1)
        self.assertTrue(self._overall().has_upcoming)
        count = NinjaEngagement.objects.count()
        rebuild()
        self.assertEqual(NinjaEngagement.objects.count(), count)


class OrganisationAndExternalEventTests(TestCase):
    """The organisation's own events (DATA_MODEL.md §12): "Organised by"
    instead of a dojo link, and registration on another website."""

    def setUp(self):
        cache.clear()
        self.org = make_dojo("CoderDojo Belgium", kind=Dojo.ORGANISATION)
        self.event = _future_event(self.org, name="Coolest Projects", places=0,
                                   external_registration_url="https://www.coolestprojects.be/register")

    def test_detail_page_links_out_instead_of_signing_up(self):
        response = self.client.get(reverse("event_detail", kwargs={"event_id": self.event.id}))
        self.assertContains(response, "Organised by CoderDojo Belgium")
        self.assertNotContains(response, reverse("dojo_detail", kwargs={"dojo_id": self.org.id}))
        self.assertContains(response, 'href="https://www.coolestprojects.be/register"')
        self.assertContains(response, "Register on coolestprojects.be")
        self.assertNotContains(response, "Sign up now")

    def test_a_dojo_event_still_links_to_its_dojo(self):
        dojo = make_dojo("Ghent")
        event = _future_event(dojo)
        response = self.client.get(reverse("event_detail", kwargs={"event_id": event.id}))
        self.assertContains(response, "Hosted by")
        self.assertContains(response, reverse("dojo_detail", kwargs={"dojo_id": dojo.id}))

    def test_signup_redirects_to_the_event_page(self):
        parent = User.objects.create(username="parent")
        self.client.force_login(parent)
        response = self.client.get(reverse("event_signup", kwargs={"event_id": self.event.id}))
        self.assertRedirects(response, reverse("event_detail", kwargs={"event_id": self.event.id}))

    def test_listed_even_without_places(self):
        from .search import upcoming_available_events

        self.assertIn(self.event, upcoming_available_events())
        response = self.client.get(reverse("event_list"))
        self.assertContains(response, "Register on coolestprojects.be")

    def test_event_filter_does_not_offer_the_organisation(self):
        response = self.client.get(reverse("event_list"))
        self.assertNotIn(self.org, response.context["dojo_choices"])



class EventLanguageTests(TestCase):
    """Sessions are given in their dojo's languages; their name and
    description can have a version per language."""

    def setUp(self):
        self.dojo = make_dojo("Brussels", languages=["nl-be", "fr-be"])
        self.event = _future_event(self.dojo, name="Codeerzaterdag", description="Leer programmeren.")
        self.event.set_translation("fr-be", "name", "Samedi code")
        self.event.save()

    def test_detail_uses_the_visitors_language(self):
        url = reverse("event_detail", kwargs={"event_id": self.event.id})
        self.assertContains(self.client.get(url, HTTP_ACCEPT_LANGUAGE="fr-be"), "Samedi code")
        dutch = self.client.get(url, HTTP_ACCEPT_LANGUAGE="nl-be")
        self.assertContains(dutch, "Codeerzaterdag")
        self.assertContains(dutch, "Nederlands (België), Français (Belgique)")

    def test_description_falls_back_to_the_main_language_with_a_note(self):
        response = self.client.get(reverse("event_detail", kwargs={"event_id": self.event.id}), HTTP_ACCEPT_LANGUAGE="fr-be")
        self.assertContains(response, "Leer programmeren.")
        self.assertContains(response, "Uniquement en Nederlands (België)")

    def test_events_list_filters_on_language(self):
        other = _future_event(make_dojo("Ghent", languages=["nl-be"]), name="Gent")
        response = self.client.get(reverse("event_list"), {"language": "fr-be"})
        events = list(response.context["events"])
        self.assertIn(self.event, events)
        self.assertNotIn(other, events)
