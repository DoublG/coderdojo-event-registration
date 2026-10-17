import threading
from datetime import timedelta
from io import BytesIO
from unittest import mock

from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection
from django.test import TestCase, TransactionTestCase
from django.urls import reverse
from django.utils import timezone
from PIL import Image

from accounts.models import Guardianship, Ninja, OrganisationRole, User
from core.testing import TempMediaMixin
from dojos.models import Dojo
from dojos.search import DEFAULT_SEARCH_ORIGIN, dojos_by_distance
from dojos.testing import make_dojo
from pathways.models import Pathway

from . import questions, registrations
from .engagement import is_aimed_at
from .models import Badge, Belt, Event, NinjaBadge, Registration, RegistrationAnswer, RegistrationCancellation
from .search import CACHE_KEY, upcoming_available_events


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
    def setUp(self):
        cache.clear()  # the unfiltered first page is cached (events.search)

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

    def test_filters_by_pathway(self):
        scratch = Pathway.objects.create(name="Scratch")
        python = Pathway.objects.create(name="Python")
        dojo = make_dojo("Ghent")
        scratch_event = _future_event(dojo, name="Scratch session")
        scratch_event.pathways.set([scratch, python])
        python_event = _future_event(dojo, name="Python session")
        python_event.pathways.set([python])
        _future_event(dojo, name="No pathway")

        response = self.client.get(reverse("event_list"), {"pathway": scratch.id})

        self.assertEqual(list(response.context["events"]), [scratch_event])
        self.assertContains(response, f'<option value="{scratch.id}" selected>Scratch</option>', html=True)

    def test_pathway_filter_lists_each_session_once(self):
        python = Pathway.objects.create(name="Python")
        event = _future_event(make_dojo("Ghent"))
        event.pathways.set([python, Pathway.objects.create(name="Scratch")])

        response = self.client.get(reverse("event_list"), {"pathway": python.id})

        self.assertEqual(list(response.context["events"]), [event])
        self.assertEqual(response.context["total_count"], 1)

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


class EventListSameDojoGroupingTests(TestCase):
    """A day with several sessions at the same dojo gets a small connecting
    marker (events/views._cluster_by_dojo_per_day, the event-row-group--same-dojo
    class in _event_results_page.html) — never for a dojo with just one session
    that day, and never across page boundaries."""

    def setUp(self):
        cache.clear()  # the unfiltered first page is cached (events.search)

    def test_same_day_same_dojo_events_are_clustered_and_marked(self):
        dojo = make_dojo("Ghent")
        other = make_dojo("Antwerp")
        now = timezone.now()
        morning = _future_event(dojo, name="Morning", start_time=now + timedelta(days=7, hours=1))
        between = _future_event(other, name="Between", start_time=now + timedelta(days=7, hours=2))
        afternoon = _future_event(dojo, name="Afternoon", start_time=now + timedelta(days=7, hours=3))

        response = self.client.get(reverse("event_list"))

        # Reordered so the same dojo's two sessions sit together, without
        # losing the other dojo's event or resorting across dojos.
        self.assertEqual(list(response.context["events"]), [morning, afternoon, between])
        # The page's own <style> block also mentions the class name (as a
        # selector), so check the actual element, not just the substring.
        self.assertContains(response, 'class="event-row-group event-row-group--same-dojo"')

    def test_a_dojo_with_a_single_session_that_day_gets_no_marker(self):
        dojo = make_dojo("Ghent")
        _future_event(dojo, name="Only session")

        response = self.client.get(reverse("event_list"))

        self.assertNotContains(response, 'class="event-row-group event-row-group--same-dojo"')

    def test_clustering_stays_within_each_day(self):
        dojo = make_dojo("Ghent")
        now = timezone.now()
        today_event = _future_event(dojo, name="Day 1", start_time=now + timedelta(days=7))
        tomorrow_event = _future_event(dojo, name="Day 2", start_time=now + timedelta(days=8))

        response = self.client.get(reverse("event_list"))

        self.assertEqual(list(response.context["events"]), [today_event, tomorrow_event])
        self.assertNotContains(response, 'class="event-row-group event-row-group--same-dojo"')

    def test_clustering_never_moves_an_event_to_a_different_page(self):
        dojo = make_dojo("Ghent")
        other = make_dojo("Antwerp")
        now = timezone.now()
        # 20 events the same day at `dojo`, filling page 1, plus one more
        # event at `other` later that same day that must land on page 2.
        for i in range(20):
            _future_event(dojo, name=f"Session {i}", start_time=now + timedelta(days=7, minutes=i))
        last = _future_event(other, name="Overflow", start_time=now + timedelta(days=7, hours=1))

        page1 = self.client.get(reverse("event_list"))
        self.assertEqual(len(page1.context["events"]), 20)
        self.assertNotIn(last, page1.context["events"])
        self.assertIsNotNone(page1.context["next_page_url"])

        page2 = self.client.get(reverse("event_list"), {"page": 2})
        self.assertEqual(list(page2.context["events"]), [last])


class EventListCacheTests(TestCase):
    """The places left on a list come from one annotated query, and the
    unfiltered first page is cached until a session or a booking changes."""

    def setUp(self):
        cache.clear()
        self.dojo = make_dojo("Ghent")

    def _book(self, event, waiting_list=False):
        position = event.registration_set.count() + 1
        return Registration.objects.create(
            event=event, ninja=Ninja.objects.create(name="Kid"), waiting_list=waiting_list, position=position
        )

    def test_places_left_reads_the_annotation_on_a_list(self):
        event = _future_event(self.dojo, places=2)
        self._book(event)
        self._book(event, waiting_list=True)
        annotated = Event.objects.with_confirmed_count().get(pk=event.pk)
        with self.assertNumQueries(0):
            self.assertEqual(annotated.places_left, 1)
        # Without it, a single event counts its own.
        self.assertEqual(Event.objects.get(pk=event.pk).places_left, 1)

    def test_more_sessions_add_no_queries(self):
        from core.testing import site_queries

        def queries():
            with site_queries() as captured:
                self.client.get(reverse("event_list"), {"date": "month"})  # filtered: not cached
            return len(captured)

        _future_event(self.dojo)
        queries()  # fills the cached pathway list behind the filter (content.cache)
        one = queries()
        for _n in range(5):
            _future_event(self.dojo)
        self.assertEqual(queries(), one)

    def test_a_booking_shows_on_the_cached_first_page_at_once(self):
        event = _future_event(self.dojo, places=1)
        self.assertEqual(self.client.get(reverse("event_list")).context["events"][0].places_left, 1)
        self._book(event)
        response = self.client.get(reverse("event_list"))
        self.assertEqual(response.context["events"][0].places_left, 0)

    def test_a_published_session_shows_on_the_cached_first_page_at_once(self):
        event = _future_event(self.dojo, status=Event.DRAFT)
        self.assertEqual(list(self.client.get(reverse("event_list")).context["events"]), [])
        event.status = Event.OPEN
        event.save()
        self.assertEqual(list(self.client.get(reverse("event_list")).context["events"]), [event])


class UpcomingSessionsWidgetViewTests(TestCase):
    def test_renders_partial(self):
        cache.clear()  # upcoming_available_events() is cached (events/search.py)
        dojo = make_dojo("Ghent")
        _future_event(dojo)
        response = self.client.get(reverse("upcoming_sessions_widget"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "events/partials/_upcoming_sessions_page.html")


class PublicCacheInvalidationTests(TestCase):
    """The dojo finder's default list and the upcoming-sessions carousel are
    cached; saving or deleting a dojo, event or registration clears them
    (events/signals.py), so a change is visible at once."""

    def setUp(self):
        cache.clear()
        self.dojo = make_dojo("Ghent")

    def _upcoming(self):
        return upcoming_available_events()

    def test_publishing_an_event_shows_it_at_once(self):
        event = _future_event(self.dojo, status=Event.DRAFT)
        self.assertNotIn(event, self._upcoming())
        event.status = Event.OPEN
        event.save()
        self.assertIn(event, self._upcoming())

    def test_an_edited_event_shows_its_new_name(self):
        event = _future_event(self.dojo)
        self.assertEqual(self._upcoming()[0].name, "Session")
        event.name = "Robot day"
        event.save()
        self.assertEqual(self._upcoming()[0].name, "Robot day")

    def test_a_deleted_event_disappears(self):
        event = _future_event(self.dojo)
        self.assertIn(event, self._upcoming())
        event.delete()
        self.assertNotIn(event, self._upcoming())

    def test_a_full_session_leaves_the_carousel_and_returns_on_a_cancellation(self):
        event = _future_event(self.dojo, places=1)
        self.assertIn(event, self._upcoming())
        registration = Registration.objects.create(
            event=event, ninja=Ninja.objects.create(name="Mila"), waiting_list=False, position=1
        )
        self.assertNotIn(event, self._upcoming())
        registration.delete()
        self.assertIn(event, self._upcoming())

    def test_an_edited_dojo_shows_in_the_finder_and_the_carousel(self):
        _future_event(self.dojo)
        self.assertEqual(dojos_by_distance(DEFAULT_SEARCH_ORIGIN)[0].name, "Ghent")
        self.assertEqual(self._upcoming()[0].dojo.name, "Ghent")
        self.dojo.name = "Gent"
        self.dojo.save()
        self.assertEqual(dojos_by_distance(DEFAULT_SEARCH_ORIGIN)[0].name, "Gent")
        self.assertEqual(self._upcoming()[0].dojo.name, "Gent")

    def test_a_dojo_that_goes_dormant_takes_its_events_off_the_carousel(self):
        event = _future_event(self.dojo)
        self.assertIn(event, self._upcoming())
        self.dojo.status = Dojo.DORMANT
        self.dojo.save()
        self.assertNotIn(event, self._upcoming())
        self.assertNotIn(self.dojo, dojos_by_distance(DEFAULT_SEARCH_ORIGIN))

    def test_the_cache_is_cleared_again_on_commit(self):
        """A visitor refilling the cache before the commit (from the old data)
        mustn't keep the change hidden."""
        event = _future_event(self.dojo, status=Event.DRAFT)
        with self.captureOnCommitCallbacks(execute=True):
            event.status = Event.OPEN
            event.save()
            cache.set(CACHE_KEY, [], 60)  # a stale refill mid-transaction
        self.assertIn(event, self._upcoming())


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
        cls.everyone = _future_event(
            cls.dojo,
            name="Everyone",
            start_time=timezone.now() + timedelta(days=8),
            end_time=timezone.now() + timedelta(days=8, hours=2),
        )

    def test_label_on_event_detail_only_for_girls_sessions(self):
        self.assertContains(
            self.client.get(reverse("event_detail", kwargs={"event_id": self.girls.id})), "Girls' session"
        )
        self.assertNotContains(
            self.client.get(reverse("event_detail", kwargs={"event_id": self.everyone.id})), "Girls' session"
        )

    def test_label_on_event_list(self):
        self.assertContains(self.client.get(reverse("event_list")), "Girls' session", count=1)

    def test_a_boy_can_sign_up_for_a_girls_session(self):
        guardian = User.objects.create(username="g1", email="g1@example.com")
        boy = Ninja.objects.create(name="Boy", gender=Ninja.BOY)
        Guardianship.objects.create(guardian=guardian, ninja=boy)
        self.client.force_login(guardian)

        self.client.post(
            reverse("event_signup", kwargs={"event_id": self.girls.id}),
            {"child": [str(boy.id)], "child_order": str(boy.id)},
        )

        self.assertTrue(Registration.objects.filter(event=self.girls, ninja=boy, waiting_list=False).exists())


class BookingTests(TestCase):
    """events.registrations: the rules, one family at a time."""

    @classmethod
    def setUpTestData(cls):
        cls.dojo = make_dojo("Ghent")
        cls.guardian = User.objects.create(username="g1", email="g1@example.com")
        cls.children = [Ninja.objects.create(name=f"Kid {n}") for n in range(3)]
        for child in cls.children:
            Guardianship.objects.create(guardian=cls.guardian, ninja=child)

    def test_a_session_closed_after_the_page_was_read_takes_nobody(self):
        event = _future_event(self.dojo)
        Event.objects.filter(pk=event.pk).update(status=Event.CLOSED)
        with self.assertRaisesMessage(registrations.RegistrationError, "Registrations for this session are closed."):
            registrations.sign_up(event, self.children[:1])
        self.assertFalse(Registration.objects.exists())

    def test_children_already_signed_up_are_skipped(self):
        event = _future_event(self.dojo)
        registrations.sign_up(event, self.children[:1])
        results = registrations.sign_up(event, self.children[:2])
        self.assertEqual([r["child"] for r in results], [self.children[1]])
        with self.assertRaisesMessage(registrations.RegistrationError, "already signed up"):
            registrations.sign_up(event, self.children[:2])

    def test_cancelling_twice_cancels_once(self):
        event = _future_event(self.dojo, places=1)
        registration = registrations.sign_up(event, self.children[:1])[0]["registration"]
        registrations.sign_up(event, self.children[1:2])
        self.assertIsNotNone(registrations.cancel(registration, cancelled_by=self.guardian))
        self.assertIsNone(registrations.cancel(registration, cancelled_by=self.guardian))
        self.assertEqual(RegistrationCancellation.objects.count(), 1)

    def test_a_waiting_child_is_only_promoted_into_a_free_place(self):
        event = _future_event(self.dojo, places=2)
        first, _second, waiting = (r["registration"] for r in registrations.sign_up(event, self.children))
        self.assertTrue(waiting.waiting_list)
        # The team lowered the places after the session filled up.
        Event.objects.filter(pk=event.pk).update(places=1)
        self.assertIsNone(registrations.cancel(first, cancelled_by=self.guardian))
        waiting.refresh_from_db()
        self.assertTrue(waiting.waiting_list)

    def test_cancelling_a_waiting_place_promotes_nobody(self):
        event = _future_event(self.dojo, places=1)
        results = registrations.sign_up(event, self.children)
        self.assertIsNone(registrations.cancel(results[1]["registration"], cancelled_by=self.guardian))
        self.assertTrue(Registration.objects.get(pk=results[2]["registration"].pk).waiting_list)


class BookingConcurrencyTests(TransactionTestCase):
    """Families clicking at the same moment (CAPACITY.md, finding 1): real
    threads, each with its own database connection, released together.
    Without the session's lock these overbooked and repeated positions."""

    def setUp(self):
        self.dojo = make_dojo("Ghent")
        self.families = []
        for n in range(10):
            guardian = User.objects.create(username=f"g{n}", email=f"g{n}@example.com")
            child = Ninja.objects.create(name=f"Kid {n}")
            Guardianship.objects.create(guardian=guardian, ninja=child)
            self.families.append((guardian, child))

    def run_together(self, *calls):
        barrier = threading.Barrier(len(calls))
        results = [None] * len(calls)

        def run(index, call):
            try:
                barrier.wait()
                results[index] = call()
            except Exception as problem:
                results[index] = problem
            finally:
                connection.close()

        threads = [threading.Thread(target=run, args=(i, call)) for i, call in enumerate(calls)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        return results

    def test_simultaneous_sign_ups_never_overbook(self):
        event = _future_event(self.dojo, places=3)
        results = self.run_together(
            *(lambda child=child: registrations.sign_up(event, [child]) for _, child in self.families)
        )
        self.assertEqual([r for r in results if isinstance(r, Exception)], [])
        booked = Registration.objects.filter(event=event)
        self.assertEqual(booked.filter(waiting_list=False).count(), 3)
        self.assertEqual(booked.filter(waiting_list=True).count(), 7)
        self.assertEqual(sorted(booked.values_list("position", flat=True)), list(range(1, 11)))
        # The confirmed places went to the first three in the queue.
        self.assertEqual(sorted(booked.filter(waiting_list=False).values_list("position", flat=True)), [1, 2, 3])

    def test_a_double_click_signs_up_once(self):
        event = _future_event(self.dojo)
        _, child = self.families[0]
        results = self.run_together(
            lambda: registrations.sign_up(event, [child]), lambda: registrations.sign_up(event, [child])
        )
        self.assertEqual(Registration.objects.filter(event=event, ninja=child).count(), 1)
        self.assertEqual(sum(isinstance(r, registrations.RegistrationError) for r in results), 1)

    def test_simultaneous_cancellations_each_promote_a_different_child(self):
        event = _future_event(self.dojo, places=2)
        for _, child in self.families[:4]:
            registrations.sign_up(event, [child])
        confirmed = list(Registration.objects.filter(event=event, waiting_list=False))
        results = self.run_together(
            *(lambda r=r: registrations.cancel(r, cancelled_by=self.families[0][0]) for r in confirmed)
        )
        self.assertEqual(len({r.pk for r in results}), 2)
        self.assertEqual(Registration.objects.filter(event=event, waiting_list=False).count(), 2)
        self.assertFalse(Registration.objects.filter(event=event, waiting_list=True).exists())

    def test_a_cancellation_and_a_sign_up_at_once_keep_the_places(self):
        event = _future_event(self.dojo, places=1)
        _, first = self.families[0]
        registration = registrations.sign_up(event, [first])[0]["registration"]
        _, second = self.families[1]
        self.run_together(
            lambda: registrations.cancel(registration, cancelled_by=self.families[0][0]),
            lambda: registrations.sign_up(event, [second]),
        )
        remaining = Registration.objects.get(event=event)
        self.assertEqual(remaining.ninja, second)
        self.assertFalse(remaining.waiting_list)


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
        self.assertEqual(
            list(Registration.objects.filter(event=event).values_list("ninja", flat=True)), [self.child.id]
        )

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

    def _refused_signup(self, data):
        """Post `data` with a sign-up that fails under the lock, so the page
        comes back with its error."""
        refused = registrations.RegistrationError("Refused under the lock.")
        with mock.patch.object(registrations, "sign_up", side_effect=refused):
            return self.client.post(reverse("event_signup", kwargs={"event_id": self.event_for_errors.id}), data)

    def test_an_error_keeps_the_children_ticked_in_their_order(self):
        """The order the children were ticked in decides who gets a place and
        who waits, so a page shown again after an error keeps it."""
        sibling = Ninja.objects.create(name="Sibling")
        Guardianship.objects.create(guardian=self.guardian, ninja=sibling)
        self.event_for_errors = _future_event(self.dojo, places=1)
        self.client.force_login(self.guardian)

        response = self._refused_signup(
            {"child": [str(self.child.id), str(sibling.id)], "child_order": f"{sibling.id},{self.child.id}"}
        )

        self.assertEqual(response.context["error"], "Refused under the lock.")
        self.assertEqual(response.context["ticked"], [sibling.id, self.child.id])
        self.assertContains(response, f'value="{sibling.id},{self.child.id}"')
        self.assertContains(response, f'name="child" value="{self.child.id}" checked>', html=False)
        self.assertContains(response, f'name="child" value="{sibling.id}" checked>', html=False)
        self.assertFalse(Registration.objects.exists())

    def test_an_error_without_script_keeps_the_ticks_in_page_order(self):
        """No script means no tick order: the page's order, as when signing up."""
        sibling = Ninja.objects.create(name="Sibling")
        Guardianship.objects.create(guardian=self.guardian, ninja=sibling)
        self.event_for_errors = _future_event(self.dojo, places=1)
        self.client.force_login(self.guardian)

        response = self._refused_signup({"child": [str(sibling.id), str(self.child.id)], "child_order": ""})

        self.assertEqual(response.context["ticked"], [sibling.id, self.child.id])

    def test_an_error_leaves_out_children_signed_up_meanwhile(self):
        sibling = Ninja.objects.create(name="Sibling")
        Guardianship.objects.create(guardian=self.guardian, ninja=sibling)
        self.event_for_errors = _future_event(self.dojo, places=5)
        Registration.objects.create(event=self.event_for_errors, ninja=self.child, waiting_list=False, position=1)
        self.client.force_login(self.guardian)

        response = self._refused_signup(
            {"child": [str(self.child.id), str(sibling.id)], "child_order": f"{self.child.id},{sibling.id}"}
        )

        self.assertEqual(response.context["ticked"], [sibling.id])

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
        self.registration = Registration.objects.create(
            event=self.event, ninja=self.ninja, waiting_list=False, position=1
        )

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

        first = self.Badge.objects.create(
            name="White Band", kind=self.Badge.MILESTONE, threshold=1, grants_belt=self.white
        )
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

    def test_a_milestone_without_a_threshold_never_breaks_marking_attendance(self):
        """Badge.clean() requires a milestone's threshold, but a row saved
        without it (an import, a fix by hand) is skipped, not a TypeError."""
        from .awards import sync_milestones

        broken = self.Badge.objects.create(name="No threshold", kind=self.Badge.MILESTONE, threshold=None)
        band = self.Badge.objects.create(name="Band", kind=self.Badge.MILESTONE, threshold=1)
        self.registration.attended = True
        self.registration.save()
        sync_milestones(self.ninja, self.mentor)
        self.assertIsNotNone(self.ninja.badges.get(badge=band).earned_date)
        self.assertFalse(self.ninja.badges.filter(badge=broken).exists())

    def test_a_mentor_awards_a_one_off_badge_once(self):
        from .awards import BadgeError, award_badge

        maker = self.Badge.objects.create(name="Game Maker")
        award = award_badge(self.ninja, maker, self.mentor, note=" Built a platformer ")

        self.assertIsNotNone(award.earned_date)
        self.assertEqual(
            (award.awarded_by, award.awarded_as_membership, award.note),
            (self.mentor.user, self.mentor, "Built a platformer"),
        )
        with self.assertRaises(BadgeError):
            award_badge(self.ninja, maker, self.champion)
        self.assertEqual(self.ninja.badges.count(), 1)

    def test_a_badge_restricted_to_specific_dojos(self):
        from dojos.testing import make_champion

        from .awards import BadgeError, award_badge

        other_dojo = make_dojo("Antwerp", champion=make_champion(username="other"))
        Registration.objects.create(event=_future_event(other_dojo), ninja=self.ninja, waiting_list=False, position=1)
        girls_only = self.Badge.objects.create(name="CoderDojo for Girls")
        girls_only.dojos.set([other_dojo])

        # self.dojo (Ghent) isn't in the restriction, even though the ninja
        # has also been there — the other dojo's own team can award it.
        with self.assertRaises(BadgeError):
            award_badge(self.ninja, girls_only, self.mentor)
        award = award_badge(self.ninja, girls_only, other_dojo.champion_membership)
        self.assertIsNotNone(award.earned_date)

    def test_the_organisation_awards_directly_with_no_dojo_or_attendance_tie(self):
        from dojos.testing import make_champion

        from .awards import BadgeError, award_badge_as_organisation

        # No registration anywhere for this ninja: the organisation's own
        # events may have no local attendance to check against.
        lone_ninja = Ninja.objects.create(name="Noor")
        organisation_only = self.Badge.objects.create(name="Coolest Projects 2026")
        organisation_only.dojos.set([make_dojo("Brussels HQ", champion=make_champion(username="hq"))])

        nobody = User.objects.create(username="parent")
        with self.assertRaises(BadgeError):
            award_badge_as_organisation(lone_ninja, organisation_only, nobody)  # no Ninjas area

        admin = User.objects.create(username="org-admin")
        OrganisationRole.objects.create(account=admin, role=OrganisationRole.ADMIN)
        award = award_badge_as_organisation(lone_ninja, organisation_only, admin, note="At the showcase")
        self.assertEqual((award.awarded_by, award.awarded_as_membership, award.note), (admin, None, "At the showcase"))
        with self.assertRaises(BadgeError):
            award_badge_as_organisation(lone_ninja, organisation_only, admin)  # already has it

    def test_badge_rules(self):
        from dojos.models import DojoMembership
        from dojos.testing import add_member, make_champion, make_mentor

        from .awards import BadgeError, award_badge

        maker = self.Badge.objects.create(name="Game Maker")
        band = self.Badge.objects.create(name="Band", kind=self.Badge.MILESTONE, threshold=1)
        dormant = add_member(self.dojo, make_mentor(username="gone"), status=DojoMembership.DORMANT)
        other_dojo = make_dojo("Antwerp", champion=make_champion(username="other"))
        for badge, membership in (
            (band, self.mentor),  # milestones follow attendance, never by hand
            (maker, dormant),  # not an active manager
            (maker, other_dojo.champion_membership),  # the ninja never came there
        ):
            with self.assertRaises(BadgeError):
                award_badge(self.ninja, badge, membership)
        self.assertFalse(self.ninja.badges.exists())

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

        self.municipality = Municipality.objects.create(
            postal_code="9000", name="Gent", center=Point(3.72, 51.05, srid=4326)
        )
        self.dojo = make_dojo("Ghent", municipality=self.municipality)
        self.event = Event.objects.create(
            name="Session",
            dojo=self.dojo,
            start_time=timezone.now(),
            end_time=timezone.now() + timedelta(hours=2),
            places=5,
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
        self.ninja = Ninja.objects.create(
            name="Emma", gender=Ninja.GIRL, date_of_birth=timezone.localdate() - timedelta(days=11 * 365)
        )

    def _session(self, days_ago, dojo=None, **fields):
        start = timezone.now() - timedelta(days=days_ago)
        return Event.objects.create(
            name=f"S{days_ago}",
            dojo=dojo or self.dojo,
            status=Event.CLOSED,
            places=20,
            start_time=start,
            end_time=start + timedelta(hours=2),
            **fields,
        )

    def _came(self, event, ninja=None, attended=True):
        Registration.objects.create(
            event=event, ninja=ninja or self.ninja, waiting_list=False, position=1, attended=attended
        )

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
        self.assertEqual(
            stages, {"Old visitor": "lapsed", "Never": "never_attended", "New": "new", "Adult": "aged_out"}
        )

    def test_registrations_share_one_object_per_session_and_dojo(self):
        """The rebuild reads every registration: each points at one shared
        session and dojo object (MEMORY_PROFILE.md), never a copy per row,
        and the children's home dojos are those same objects."""
        from core.testing import site_queries
        from dojos.models import Dojo

        from .engagement import _registrations_by_ninja

        other = Ninja.objects.create(name="Noor", home_dojo=self.dojo)
        session, later = self._session(30), self._session(10)
        for ninja in (self.ninja, other):
            self._came(session, ninja=ninja)
            self._came(later, ninja=ninja, attended=False)
        dojos = Dojo.objects.in_bulk()
        with site_queries() as captured:
            came, no_shows, _upcoming = _registrations_by_ninja(timezone.now(), dojos)
        self.assertEqual(len(captured), 3)  # sessions, the marked sessions, the registrations
        self.assertIs(came[self.ninja.pk][session.pk][0], came[other.pk][session.pk][0])
        self.assertIs(no_shows[self.ninja.pk][0], no_shows[other.pk][0])
        self.assertIs(came[self.ninja.pk][session.pk][0].dojo, dojos[self.dojo.pk])
        self.assertEqual(self._overall(other).main_dojo, self.dojo)

    def test_a_session_nobody_marked_counts_a_confirmed_place(self):
        unmarked = self._session(30)
        Registration.objects.create(event=unmarked, ninja=self.ninja, waiting_list=False, position=1)
        row = self._overall()
        self.assertEqual(row.attended_180d, 1)
        self.assertFalse(row.from_marked_attendance)

    def test_a_boy_does_not_miss_a_girls_session_or_one_for_older_children(self):
        boy = Ninja.objects.create(
            name="Liam", gender=Ninja.BOY, date_of_birth=timezone.localdate() - timedelta(days=8 * 365)
        )
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

    def _snapshot(self):
        from .models import NinjaEngagement

        return sorted(
            NinjaEngagement.objects.values_list(
                "ninja_id", "dojo_id", "main_dojo_id", "stage", "attended_180d", "offered_180d", "missed_in_a_row"
            ),
            key=lambda row: (row[0], row[1] or 0),
        )

    def test_batches_give_the_same_rows_as_one_batch(self):
        """The rebuild works a batch of children at a time (CAPACITY.md):
        any batch size gives the same rows, and a stage change is recorded
        once, in the batch of that child."""
        from .engagement import rebuild
        from .models import NinjaEngagement, NinjaEngagementChange

        elsewhere = make_dojo("Antwerp")
        children = [self.ninja] + [
            Ninja.objects.create(name=f"Child {n}", home_dojo=self.dojo if n % 2 else None) for n in range(5)
        ]
        sessions = [self._session(days) for days in (150, 120, 90, 60)] + [self._session(30, dojo=elsewhere)]
        for n, child in enumerate(children):
            for session in sessions[n % 3 :]:
                self._came(session, ninja=child, attended=bool(n % 2) or None)
        self.assertEqual(rebuild(batch_size=1000), NinjaEngagement.objects.count())
        whole = self._snapshot()
        self.assertEqual(rebuild(batch_size=2), len(whole))
        self.assertEqual(self._snapshot(), whole)

        NinjaEngagement.objects.filter(ninja=children[1], dojo=None).update(stage=NinjaEngagement.LAPSED)
        rebuild(batch_size=2)
        rebuild(batch_size=1)
        self.assertEqual(NinjaEngagementChange.objects.filter(ninja=children[1]).count(), 1)
        self.assertEqual(NinjaEngagementChange.objects.count(), 1)

    def test_the_batch_size_is_a_setting(self):
        from unittest import mock

        from django.conf import settings
        from django.test import override_settings

        from . import engagement

        for _ in range(4):
            Ninja.objects.create(name="Child")
        with (
            override_settings(ENGAGEMENT_REBUILD_BATCH_SIZE=2),
            mock.patch.object(engagement, "_rebuild_batch", return_value=0) as batch,
        ):
            engagement.rebuild()
        self.assertEqual(batch.call_count, 3)  # 5 children, 2 at a time
        self.assertEqual(settings.ENGAGEMENT_REBUILD_BATCH_SIZE, 500)

    def test_a_batch_reads_only_its_childrens_registrations(self):
        from core.testing import site_queries

        from .engagement import _registrations_by_ninja

        other = Ninja.objects.create(name="Noor")
        session = self._session(30)
        self._came(session)
        self._came(session, ninja=other)
        came, _no_shows, _upcoming = _registrations_by_ninja(
            timezone.now(), Dojo.objects.in_bulk(), ninjas=(other.pk, other.pk)
        )
        self.assertEqual(set(came), {other.pk})
        with site_queries() as captured:
            _registrations_by_ninja(timezone.now(), {}, events={}, marked_events=set(), ninjas=(0, 0))
        self.assertEqual(len(captured), 1)  # only the registrations: the rest comes in once

    def test_a_stuck_rebuild_is_not_handed_out_again(self):
        """Acknowledged when it starts and stopped after ten minutes: a run
        that dies or hangs isn't retried the same night (CAPACITY.md)."""
        from .tasks import rebuild_engagement

        self.assertFalse(rebuild_engagement.acks_late)
        self.assertEqual(rebuild_engagement.time_limit, 600)


class OrganisationAndExternalEventTests(TestCase):
    """The organisation's own events (DATA_MODEL.md §12): "Organised by"
    instead of a dojo link, and registration on another website."""

    def setUp(self):
        cache.clear()
        self.org = make_dojo("CoderDojo Belgium", kind=Dojo.ORGANISATION)
        self.event = _future_event(
            self.org,
            name="Coolest Projects",
            places=0,
            external_registration_url="https://www.coolestprojects.be/register",
        )

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

    def test_event_filter_offers_the_organisation_as_one_entry(self):
        dojo = make_dojo("Ghent")
        response = self.client.get(reverse("event_list"))
        choices = dict(response.context["form"].fields["dojo"].choices)
        self.assertEqual(choices["organisation"], "CoderDojo Belgium (organisation)")
        self.assertIn(dojo.pk, choices)
        # The organisation dojo itself is never listed like a dojo.
        self.assertNotIn(self.org.pk, choices)

    def test_event_filter_shows_only_the_organisations_events(self):
        other_org = make_dojo("CoderDojo Girlz", kind=Dojo.ORGANISATION)
        girlz_event = _future_event(other_org, name="Girlz day")
        _future_event(make_dojo("Ghent"))

        response = self.client.get(reverse("event_list"), {"dojo": "organisation"})

        self.assertEqual(set(response.context["events"]), {self.event, girlz_event})
        self.assertContains(response, "Filtered by:")
        self.assertContains(response, "<strong>CoderDojo Belgium (organisation)</strong>", html=True)

    def test_event_filter_rejects_the_organisation_dojos_own_id(self):
        _future_event(make_dojo("Ghent"))
        response = self.client.get(reverse("event_list"), {"dojo": self.org.pk})
        # Not a choice: the form is invalid, so no filter applies.
        self.assertFalse(response.context["form"].is_valid())
        self.assertEqual(len(response.context["events"]), 2)


class EventListFilterChipsTests(TestCase):
    """Every filter the events list applies shows as its own chip (core/partials/_active_filters.html)."""

    def test_no_chips_on_the_unfiltered_list(self):
        response = self.client.get(reverse("event_list"))
        self.assertEqual(response.context["active_filters"], [])
        self.assertNotContains(response, "Filtered by:")

    def test_each_filter_has_a_chip_that_removes_only_it(self):
        dojo = make_dojo("Ghent")
        path = reverse("event_list")
        response = self.client.get(
            path, {"location": "Gent", "dojo": dojo.pk, "date": "week", "age": "7-9", "language": "", "page": "2"}
        )
        chips = response.context["active_filters"]
        self.assertEqual(
            [(chip.label, chip.value) for chip in chips],
            [("Location", "Gent"), ("Dojo", "Ghent"), ("Date", "This week"), ("Age", "7–9")],
        )
        by_label = {chip.label: chip.remove_url for chip in chips}
        # Empty fields and the page are left out of every link.
        self.assertEqual(by_label["Dojo"], f"{path}?location=Gent&date=week&age=7-9")
        self.assertEqual(by_label["Age"], f"{path}?location=Gent&dojo={dojo.pk}&date=week")
        self.assertContains(
            response, f'<a class="cd-active-filters__clear body-sm" href="{path}">Clear all</a>', html=True
        )

    def test_an_invalid_search_applies_and_shows_no_filter(self):
        response = self.client.get(reverse("event_list"), {"date": "someday", "location": "Gent"})
        self.assertEqual(response.context["active_filters"], [])


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
        self.assertContains(dutch, "Nederlands, Français")

    def test_description_falls_back_to_the_main_language_with_a_note(self):
        response = self.client.get(
            reverse("event_detail", kwargs={"event_id": self.event.id}), HTTP_ACCEPT_LANGUAGE="fr-be"
        )
        self.assertContains(response, "Leer programmeren.")
        self.assertContains(response, "Uniquement en Nederlands")

    def test_events_list_filters_on_language(self):
        other = _future_event(make_dojo("Ghent", languages=["nl-be"]), name="Gent")
        response = self.client.get(reverse("event_list"), {"language": "fr-be"})
        events = list(response.context["events"])
        self.assertIn(self.event, events)
        self.assertNotIn(other, events)


def _png():
    buffer = BytesIO()
    Image.new("RGB", (8, 8), "orange").save(buffer, "PNG")
    return SimpleUploadedFile("game.png", buffer.getvalue(), content_type="image/png")


class ManageAwardsTests(TempMediaMixin, TestCase):
    """The organisation dashboard's Awards page (events.manage): only
    organisation admins create and edit awards; dojo teams only award them."""

    def setUp(self):
        super().setUp()
        self.admin = User.objects.create(username="admin")
        OrganisationRole.objects.create(account=self.admin, role=OrganisationRole.ADMIN)

    def test_admin_uploads_a_new_one_off_award(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse("manage_badge_list"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "events/manage/badge_list.html")
        response = self.client.post(
            reverse("manage_badge_create"),
            {
                "name": "Game Maker",
                "kind": Badge.ONE_OFF,
                "criteria": "Build and share a playable game.",
                "tr__nl-be__name": "Spelmaker",
                "icon": _png(),
            },
        )
        self.assertRedirects(response, reverse("manage_badge_list"))
        badge = Badge.objects.get(name="Game Maker")
        self.assertEqual(badge.kind, Badge.ONE_OFF)
        self.assertTrue(badge.icon.name.startswith("awards/"))
        self.assertEqual(badge.translation_for("nl-be", "name"), "Spelmaker")

    def test_restricting_to_specific_dojos(self):
        from dojos.testing import make_champion

        organisation = make_dojo("CoderDojo Belgium", champion=make_champion(username="org"), kind=Dojo.ORGANISATION)
        self.client.force_login(self.admin)
        self.client.post(
            reverse("manage_badge_create"),
            {"name": "CoderDojo for Girls", "kind": Badge.ONE_OFF, "dojos": [organisation.id]},
        )
        badge = Badge.objects.get(name="CoderDojo for Girls")
        self.assertEqual(list(badge.dojos.all()), [organisation])
        response = self.client.get(reverse("manage_badge_list"))
        self.assertContains(response, organisation.name)

        # Switching to a milestone drops the restriction: it's never
        # awarded by hand, so which dojos may award it is moot.
        self.client.post(
            reverse("manage_badge_detail", kwargs={"badge_id": badge.id}),
            {"name": "CoderDojo for Girls", "kind": Badge.MILESTONE, "threshold": "3", "dojos": [organisation.id]},
        )
        badge.refresh_from_db()
        self.assertFalse(badge.dojos.exists())

    def test_a_standard_icon_is_linked_and_svg_uploads_are_refused(self):
        self.client.force_login(self.admin)
        self.client.post(
            reverse("manage_badge_create"),
            {"name": "Coolest", "kind": Badge.ONE_OFF, "library_icon": "coolest-projects.svg"},
        )
        self.assertEqual(Badge.objects.get(name="Coolest").icon.name, "library/awards/coolest-projects.svg")
        svg = SimpleUploadedFile(
            "x.svg",
            b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>',
            content_type="image/svg+xml",
        )
        response = self.client.post(
            reverse("manage_badge_create"), {"name": "Sneaky", "kind": Badge.ONE_OFF, "icon": svg}
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Badge.objects.filter(name="Sneaky").exists())

    def test_milestone_needs_a_threshold_and_can_grant_a_belt(self):
        belt = Belt.objects.create(name="Yellow belt", level=1)
        self.client.force_login(self.admin)
        response = self.client.post(reverse("manage_badge_create"), {"name": "Blue Band", "kind": Badge.MILESTONE})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Badge.objects.exists())
        self.client.post(
            reverse("manage_badge_create"),
            {
                "name": "Blue Band",
                "kind": Badge.MILESTONE,
                "threshold": "20",
                "grants_belt": belt.id,
            },
        )
        badge = Badge.objects.get(name="Blue Band")
        self.assertEqual((badge.threshold, badge.grants_belt), (20, belt))

    def test_switching_to_one_off_drops_the_milestone_fields(self):
        belt = Belt.objects.create(name="Yellow belt", level=1)
        badge = Badge.objects.create(name="Band", kind=Badge.MILESTONE, threshold=3, grants_belt=belt)
        self.client.force_login(self.admin)
        response = self.client.post(
            reverse("manage_badge_detail", kwargs={"badge_id": badge.id}),
            {
                "name": "Band",
                "kind": Badge.ONE_OFF,
                "threshold": "3",
                "grants_belt": belt.id,
            },
        )
        self.assertRedirects(response, reverse("manage_badge_list"))
        badge.refresh_from_db()
        self.assertEqual((badge.kind, badge.threshold, badge.grants_belt), (Badge.ONE_OFF, None, None))

    def test_an_award_ninjas_have_is_not_removed(self):
        kept = Badge.objects.create(name="Kept")
        NinjaBadge.objects.create(
            ninja=Ninja.objects.create(name="Ada", date_of_birth="2015-01-01"),
            badge=kept,
            earned_date=timezone.localdate(),
        )
        unused = Badge.objects.create(name="Unused")
        self.client.force_login(self.admin)
        self.client.post(reverse("manage_badge_delete", kwargs={"badge_id": kept.id}))
        self.client.post(reverse("manage_badge_delete", kwargs={"badge_id": unused.id}))
        self.assertEqual(list(Badge.objects.values_list("name", flat=True)), ["Kept"])

    def test_only_organisation_admins(self):
        badge = Badge.objects.create(name="Game Maker")
        board = User.objects.create(username="board")
        OrganisationRole.objects.create(account=board, role=OrganisationRole.BOARD)
        champion = User.objects.create(username="champion")
        make_dojo("Leuven", champion=champion)
        for user in (User.objects.create(username="parent"), board, champion):
            self.client.force_login(user)
            for url in (
                reverse("manage_badge_list"),
                reverse("manage_badge_create"),
                reverse("manage_badge_detail", kwargs={"badge_id": badge.id}),
            ):
                self.assertEqual(self.client.get(url).status_code, 404)
            self.client.post(reverse("manage_badge_create"), {"name": "Sneaky", "kind": Badge.ONE_OFF})
            self.client.post(reverse("manage_badge_delete", kwargs={"badge_id": badge.id}))
        self.assertEqual(list(Badge.objects.values_list("name", flat=True)), ["Game Maker"])


class AssignAwardsTests(TestCase):
    """The organisation dashboard's Assign awards page (events.manage,
    events.awards.award_badge_as_organisation): award a one-off badge
    directly to a ninja, with no dojo or attendance tie."""

    def setUp(self):
        self.admin = User.objects.create(username="admin")
        OrganisationRole.objects.create(account=self.admin, role=OrganisationRole.ADMIN)
        self.ninja = Ninja.objects.create(name="Mila", family_name="Peeters")
        self.maker = Badge.objects.create(name="Game Maker")
        self.band = Badge.objects.create(name="White Band", kind=Badge.MILESTONE, threshold=1)

    def test_search_finds_a_ninja_by_name(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse("manage_badge_assign"), {"q": "Peeters"})
        self.assertContains(response, "Mila Peeters")
        self.assertTemplateUsed(response, "events/manage/badge_assign.html")
        no_match = self.client.get(reverse("manage_badge_assign"), {"q": "Nobody"})
        self.assertNotContains(no_match, "Mila Peeters")

    def test_typeahead_gets_back_just_the_results(self):
        """The search box's htmx request (as-you-type) gets only the results
        partial, never the whole page — a plain GET (no JavaScript) still
        gets the whole page, same results included."""
        self.client.force_login(self.admin)
        response = self.client.get(reverse("manage_badge_assign"), {"q": "Peeters"}, HTTP_HX_REQUEST="true")
        self.assertContains(response, "Mila Peeters")
        self.assertTemplateUsed(response, "events/manage/_badge_assign_results.html")
        self.assertTemplateNotUsed(response, "events/manage/badge_assign.html")

    def test_awards_a_badge_with_no_registration_at_all(self):
        self.client.force_login(self.admin)
        url = reverse("manage_badge_assign_ninja", kwargs={"ninja_id": self.ninja.id})
        response = self.client.post(url, {"badge": self.maker.id, "note": "At the showcase"})
        self.assertRedirects(response, url)
        award = self.ninja.badges.get(badge=self.maker)
        self.assertEqual(
            (award.awarded_by, award.awarded_as_membership, award.note), (self.admin, None, "At the showcase")
        )

    def test_only_one_offs_not_yet_earned_are_offered(self):
        self.client.force_login(self.admin)
        url = reverse("manage_badge_assign_ninja", kwargs={"ninja_id": self.ninja.id})
        self.client.post(url, {"badge": self.maker.id})
        response = self.client.get(url)
        self.assertNotContains(response, f'value="{self.maker.id}"')
        self.assertNotContains(response, f'value="{self.band.id}"')
        self.assertContains(response, "Game Maker")  # in "Already earned" now, not the picker

    def test_dojo_restricted_badges_are_still_offered(self):
        from dojos.testing import make_champion

        other_dojo = make_dojo("Antwerp", champion=make_champion(username="other"))
        self.maker.dojos.set([other_dojo])
        self.client.force_login(self.admin)
        url = reverse("manage_badge_assign_ninja", kwargs={"ninja_id": self.ninja.id})
        self.client.post(url, {"badge": self.maker.id})
        self.assertTrue(self.ninja.badges.filter(badge=self.maker, earned_date__isnull=False).exists())

    def test_only_organisation_admins(self):
        board = User.objects.create(username="board")
        OrganisationRole.objects.create(account=board, role=OrganisationRole.BOARD)
        self.client.force_login(board)
        self.assertEqual(self.client.get(reverse("manage_badge_assign")).status_code, 404)
        url = reverse("manage_badge_assign_ninja", kwargs={"ninja_id": self.ninja.id})
        self.assertEqual(self.client.get(url).status_code, 404)
        self.client.post(url, {"badge": self.maker.id})
        self.assertFalse(self.ninja.badges.exists())


class SeedUpcomingRegistrationsTests(TestCase):
    """The seeder behind the waiting-list demo data: three filled sessions
    and children signed up at several dojos, rerun-safe."""

    def setUp(self):
        from django.contrib.gis.geos import Point

        places = [(3.72, 51.05), (3.75, 51.06), (3.78, 51.07), (3.81, 51.08)]
        self.dojos = [make_dojo(f"Dojo {i}", location=Point(x, y, srid=4326)) for i, (x, y) in enumerate(places)]
        self.events = [_future_event(dojo, places=p) for dojo, p in zip(self.dojos, [3, 3, 3, 30], strict=True)]
        guardian = User.objects.create(username="parent")
        # Most children at the first dojos, so those are the ones filled.
        for i in range(24):
            ninja = Ninja.objects.create(name=f"Kid {i}", home_dojo=self.dojos[min(i // 6, 3)])
            Guardianship.objects.create(guardian=guardian, ninja=ninja)

    def _seed(self):
        from io import StringIO

        from django.core.management import call_command

        call_command("seed_upcoming_registrations", stdout=StringIO())

    def test_fills_sessions_for_the_waiting_list_and_signs_up_at_several_dojos(self):
        from unittest import mock

        # Every child also picks every nearby dojo, so the draw can't leave
        # nobody at a second one.
        command = "events.management.commands.seed_upcoming_registrations"
        with mock.patch(f"{command}.OTHER_DOJOS_MIN", 3), mock.patch(f"{command}.OTHER_DOJOS_MAX", 3):
            self._seed()
        full, exactly_full, one_left, other = self.events
        self.assertEqual(full.registration_set.filter(waiting_list=False).count(), 3)
        self.assertEqual(full.registration_set.filter(waiting_list=True).count(), 4)
        self.assertEqual(list(full.registration_set.values_list("position", flat=True)), list(range(1, 8)))
        self.assertEqual(exactly_full.places_left, 0)
        self.assertFalse(exactly_full.registration_set.filter(waiting_list=True).exists())
        self.assertEqual(one_left.places_left, 1)
        # The others are never filled up.
        self.assertFalse(other.registration_set.filter(waiting_list=True).exists())
        several = [
            n
            for n in Ninja.objects.all()
            if Registration.objects.filter(ninja=n).values("event__dojo").distinct().count() > 1
        ]
        self.assertTrue(several)

    def test_a_rerun_adds_nothing(self):
        self._seed()
        count = Registration.objects.count()
        self._seed()
        self.assertEqual(Registration.objects.count(), count)


class SignUpQuestionsTests(TestCase):
    """events.questions and the answers saved by events.registrations.sign_up
    (DATA_MODEL.md §29)."""

    @classmethod
    def setUpTestData(cls):
        cls.dojo = make_dojo("Ghent")
        cls.guardian = User.objects.create(username="g1", email="g1@example.com")
        cls.children = [Ninja.objects.create(name=f"Kid {n}") for n in range(3)]
        for child in cls.children:
            Guardianship.objects.create(guardian=cls.guardian, ninja=child)

    def test_at_most_five_questions(self):
        event = _future_event(self.dojo)
        for n in range(questions.MAX_QUESTIONS):
            questions.add_question(event, f"Question {n}?")
        with self.assertRaisesMessage(questions.QuestionError, "at most 5"):
            questions.add_question(event, "One too many?")
        self.assertEqual(event.questions.count(), questions.MAX_QUESTIONS)

    def test_a_question_needs_text_and_a_session_that_signs_up_here(self):
        event = _future_event(self.dojo)
        with self.assertRaises(questions.QuestionError):
            questions.add_question(event, "   ")
        external = _future_event(self.dojo, external_registration_url="https://example.com/")
        with self.assertRaises(questions.QuestionError):
            questions.add_question(external, "Own laptop?")

    def test_translations_are_kept_for_the_dojos_other_languages(self):
        self.dojo.languages = ["nl-be", "fr-be"]
        self.dojo.save()
        event = _future_event(self.dojo)
        question = questions.add_question(event, "Eigen laptop?", {"fr-be": "Propre ordinateur ?", "en-us": "x"})
        self.assertEqual(question.translations, {"fr-be": {"text": "Propre ordinateur ?"}})

    def test_moving_and_removing(self):
        event = _future_event(self.dojo)
        first = questions.add_question(event, "First?")
        second = questions.add_question(event, "Second?")
        questions.move_question(second, "up")
        self.assertEqual([q.text for q in event.questions.all()], ["Second?", "First?"])
        questions.move_question(second, "up")  # already first: nothing changes
        self.assertEqual([q.text for q in event.questions.all()], ["Second?", "First?"])
        registration = registrations.sign_up(
            event, self.children[:1], answers={self.children[0].id: {first.id: True, second.id: False}}
        )[0]["registration"]
        questions.remove_question(first)
        self.assertEqual(list(registration.answers.values_list("question", flat=True)), [second.id])

    def test_sign_up_saves_every_childs_answers(self):
        event = _future_event(self.dojo, places=1)
        laptop = questions.add_question(event, "Own laptop?")
        a, b = self.children[:2]
        results = registrations.sign_up(event, [a, b], answers={a.id: {laptop.id: True}, b.id: {laptop.id: False}})
        self.assertEqual(
            {r["child"].id: list(r["registration"].answers.values_list("answer", flat=True)) for r in results},
            {a.id: [True], b.id: [False]},
        )
        self.assertEqual(
            questions.totals(event),
            [{"question": laptop, "yes": 1, "no": 0, "waiting_yes": 0, "waiting_no": 1}],
        )

    def test_a_missing_answer_saves_nothing(self):
        """A question added while the form was open: its answer is missing,
        so nobody is signed up and the family checks the questions again."""
        event = _future_event(self.dojo)
        laptop = questions.add_question(event, "Own laptop?")
        added_later = questions.add_question(event, "Staying for lunch?")
        a = self.children[0]
        with self.assertRaises(registrations.QuestionsChanged):
            registrations.sign_up(event, [a], answers={a.id: {laptop.id: True}})
        self.assertFalse(Registration.objects.exists())
        registrations.sign_up(event, [a], answers={a.id: {laptop.id: True, added_later.id: False}})
        self.assertEqual(RegistrationAnswer.objects.count(), 2)

    def test_a_session_without_questions_needs_no_answers(self):
        event = _future_event(self.dojo)
        registrations.sign_up(event, self.children[:1])
        self.assertFalse(RegistrationAnswer.objects.exists())

    def test_cancelling_deletes_the_answers_and_promotion_keeps_them(self):
        event = _future_event(self.dojo, places=1)
        laptop = questions.add_question(event, "Own laptop?")
        a, b = self.children[:2]
        first, waiting = (
            r["registration"]
            for r in registrations.sign_up(event, [a, b], answers={a.id: {laptop.id: True}, b.id: {laptop.id: False}})
        )
        registrations.cancel(first, cancelled_by=self.guardian)
        self.assertFalse(RegistrationAnswer.objects.filter(registration_id=first.id).exists())
        waiting.refresh_from_db()
        self.assertFalse(waiting.waiting_list)
        self.assertEqual(list(waiting.answers.values_list("answer", flat=True)), [False])

    def test_a_new_session_copies_the_latest_sessions_questions(self):
        older = _future_event(self.dojo, start_time=timezone.now() + timedelta(days=1))
        questions.add_question(older, "Older?")
        latest = _future_event(self.dojo, start_time=timezone.now() + timedelta(days=3))
        questions.add_question(latest, "Own laptop?")
        questions.add_question(latest, "Lunch?")
        new = _future_event(self.dojo, start_time=timezone.now() + timedelta(days=10))
        questions.copy_from_latest(new)
        self.assertEqual([q.text for q in new.questions.all()], ["Own laptop?", "Lunch?"])
        # Never twice, and never to a session that signs up elsewhere.
        questions.copy_from_latest(new)
        self.assertEqual(new.questions.count(), 2)
        external = _future_event(self.dojo, external_registration_url="https://example.com/")
        questions.copy_from_latest(external)
        self.assertFalse(external.questions.exists())

    def test_the_familys_data_export_has_the_answers(self):
        from privacy.export import export_person

        event = _future_event(self.dojo)
        laptop = questions.add_question(event, "Own laptop?")
        a = self.children[0]
        registrations.sign_up(event, [a], answers={a.id: {laptop.id: True}})
        records = export_person(self.guardian)["data"]["events.RegistrationAnswer"]["records"]
        self.assertEqual([r["answer"] for r in records], [True])


class SignUpQuestionsViewTests(TestCase):
    """The sign-up page with the session's yes/no questions."""

    @classmethod
    def setUpTestData(cls):
        cls.dojo = make_dojo("Ghent")
        cls.guardian = User.objects.create(username="g1", email="g1@example.com")
        cls.emma = Ninja.objects.create(name="Emma")
        cls.lars = Ninja.objects.create(name="Lars")
        for child in (cls.emma, cls.lars):
            Guardianship.objects.create(guardian=cls.guardian, ninja=child)

    def setUp(self):
        self.event = _future_event(self.dojo)
        self.laptop = questions.add_question(self.event, "Will your child bring their own laptop?")
        self.url = reverse("event_signup", kwargs={"event_id": self.event.id})
        self.client.force_login(self.guardian)

    def name(self, child):
        return f"q-{child.id}-{self.laptop.id}"

    def test_each_child_gets_the_questions(self):
        response = self.client.get(self.url)
        self.assertContains(response, "Will your child bring their own laptop?", count=2)
        self.assertContains(response, f'name="{self.name(self.emma)}" value="yes"')
        self.assertContains(response, f'name="{self.name(self.lars)}" value="no"')

    def test_a_session_without_questions_shows_none(self):
        event = _future_event(self.dojo)
        response = self.client.get(reverse("event_signup", kwargs={"event_id": event.id}))
        self.assertNotContains(response, 'class="child-questions"')

    def test_signing_up_saves_the_answers_and_shows_them(self):
        response = self.client.post(
            self.url,
            {
                "child": [str(self.emma.id), str(self.lars.id)],
                "child_order": f"{self.lars.id},{self.emma.id}",
                self.name(self.emma): "yes",
                self.name(self.lars): "no",
            },
        )
        self.assertEqual(response.status_code, 200)
        answers = dict(RegistrationAnswer.objects.values_list("registration__ninja", "answer"))
        self.assertEqual(answers, {self.emma.id: True, self.lars.id: False})
        self.assertEqual(
            [r["answers"] for r in response.context["results"]], [[(self.laptop, False)], [(self.laptop, True)]]
        )

    def test_a_missing_answer_keeps_the_form_filled_in_and_the_order(self):
        response = self.client.post(
            self.url,
            {
                "child": [str(self.emma.id), str(self.lars.id)],
                "child_order": f"{self.lars.id},{self.emma.id}",
                self.name(self.emma): "yes",
            },
        )
        self.assertFalse(Registration.objects.exists())
        self.assertEqual(response.context["error"], "Answer every question for each child you sign up.")
        self.assertEqual(response.context["ticked"], [self.lars.id, self.emma.id])
        fields = {entry["child"].id: entry["questions"][0] for entry in response.context["children"]}
        self.assertEqual((fields[self.emma.id]["value"], fields[self.emma.id]["error"]), ("yes", False))
        self.assertEqual((fields[self.lars.id]["value"], fields[self.lars.id]["error"]), ("", True))
        self.assertContains(response, f'id="{self.name(self.lars)}-error"')

    def test_an_unticked_childs_answers_are_not_needed(self):
        self.client.post(self.url, {"child": [str(self.emma.id)], self.name(self.emma): "no"})
        self.assertEqual(list(RegistrationAnswer.objects.values_list("answer", flat=True)), [False])

    def test_questions_changed_under_the_lock(self):
        """A question added after the form was read: the post's answers
        were complete for the old list, so the page comes back with the
        new question to answer."""
        form_post = {"child": [str(self.emma.id)], self.name(self.emma): "yes"}
        with mock.patch("events.views.SignUpForm.clean", autospec=True) as clean:
            lunch = questions.add_question(self.event, "Staying for lunch?")

            def stale(form):
                return {"selected": [self.emma], "answers": {self.emma.id: {self.laptop.id: True}}}

            clean.side_effect = stale
            response = self.client.post(self.url, form_post)
        self.assertFalse(Registration.objects.exists())
        self.assertIn("questions for this session changed", response.context["error"])
        texts = [item["question"].text for item in response.context["children"][0]["questions"]]
        self.assertEqual(texts, ["Will your child bring their own laptop?", lunch.text])


class ChangeAnswersTests(TestCase):
    """Changing a child's answers from the account page (DATA_MODEL.md §29,
    phase 2): events.questions.change_answers and the family's page."""

    @classmethod
    def setUpTestData(cls):
        cls.dojo = make_dojo("Ghent")
        cls.guardian = User.objects.create(username="g1", email="g1@example.com")
        cls.emma = Ninja.objects.create(name="Emma")
        Guardianship.objects.create(guardian=cls.guardian, ninja=cls.emma)

    def setUp(self):
        self.event = _future_event(self.dojo)
        self.laptop = questions.add_question(self.event, "Own laptop?")
        self.registration = registrations.sign_up(
            self.event, [self.emma], answers={self.emma.id: {self.laptop.id: True}}
        )[0]["registration"]
        self.url = reverse("registration_answers", kwargs={"registration_id": self.registration.id})
        self.client.force_login(self.guardian)

    def answers(self):
        return dict(self.registration.answers.values_list("question__text", "answer"))

    def test_changing_an_answer(self):
        self.assertTrue(questions.change_answers(self.registration, {self.laptop.id: False}))
        self.assertEqual(self.answers(), {"Own laptop?": False})
        self.assertFalse(questions.change_answers(self.registration, {self.laptop.id: False}))

    def test_answering_a_question_added_later(self):
        lunch = questions.add_question(self.event, "Lunch?")
        with self.assertRaises(questions.QuestionError):
            questions.change_answers(self.registration, {self.laptop.id: True})
        questions.change_answers(self.registration, {self.laptop.id: True, lunch.id: True})
        self.assertEqual(self.answers(), {"Own laptop?": True, "Lunch?": True})

    def test_not_once_the_session_started(self):
        Event.objects.filter(pk=self.event.pk).update(start_time=timezone.now() - timedelta(minutes=5))
        with self.assertRaisesMessage(questions.QuestionError, "has started"):
            questions.change_answers(self.registration, {self.laptop.id: False})
        self.assertEqual(self.client.get(self.url).status_code, 404)

    def test_the_page_shows_and_saves_the_answers(self):
        response = self.client.get(self.url)
        self.assertContains(response, f'name="q-{self.laptop.id}" value="yes" checked')
        response = self.client.post(self.url, {f"q-{self.laptop.id}": "no"})
        self.assertRedirects(response, reverse("account_home"))
        self.assertEqual(self.answers(), {"Own laptop?": False})

    def test_a_change_is_in_the_audit_log_and_tells_the_team(self):
        from auditlog.models import LogEntry

        from dojos.testing import make_champion
        from notifications.models import Notification

        champion = make_champion(username="champ")
        dojo = make_dojo("Leuven", champion=champion)
        event = _future_event(dojo)
        laptop = questions.add_question(event, "Own laptop?")
        self.client.post(
            reverse("event_signup", kwargs={"event_id": event.id}),
            {"child": [str(self.emma.id)], f"q-{self.emma.id}-{laptop.id}": "yes"},
        )
        registration = Registration.objects.get(event=event, ninja=self.emma)
        answer = registration.answers.get()
        url = reverse("registration_answers", kwargs={"registration_id": registration.id})
        self.client.post(url, {f"q-{laptop.id}": "no"})
        entries = LogEntry.objects.get_for_object(answer).order_by("timestamp")
        self.assertEqual(
            [(e.action, e.actor_id) for e in entries],
            [(LogEntry.Action.CREATE, self.guardian.id), (LogEntry.Action.UPDATE, self.guardian.id)],
        )
        self.assertEqual(entries.last().changes_dict["answer"], ["True", "False"])
        notification = Notification.objects.get(recipient=champion)
        self.assertIn("Emma", notification.text)
        self.assertEqual(
            notification.url, reverse("dojo_event_attendance", kwargs={"dojo_id": dojo.id, "event_id": event.id})
        )
        # Saving the same answers again changes nothing and tells nobody.
        self.client.post(url, {f"q-{laptop.id}": "no"})
        self.assertEqual(Notification.objects.filter(recipient=champion).count(), 1)

    def test_a_missing_answer_is_marked(self):
        lunch = questions.add_question(self.event, "Lunch?")
        response = self.client.get(self.url)
        self.assertContains(response, "New question")
        response = self.client.post(self.url, {f"q-{self.laptop.id}": "no"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, f'id="q-{lunch.id}-error"')
        self.assertEqual(self.answers(), {"Own laptop?": True})

    def test_another_familys_child_is_a_404(self):
        self.client.force_login(User.objects.create(username="g2", email="g2@example.com"))
        self.assertEqual(self.client.get(self.url).status_code, 404)
        self.assertEqual(self.client.post(self.url, {f"q-{self.laptop.id}": "no"}).status_code, 404)
        self.assertEqual(self.answers(), {"Own laptop?": True})

    def test_a_session_without_questions_has_no_page(self):
        other = _future_event(self.dojo)
        registration = registrations.sign_up(other, [self.emma])[0]["registration"]
        url = reverse("registration_answers", kwargs={"registration_id": registration.id})
        self.assertEqual(self.client.get(url).status_code, 404)

    def test_the_account_page_links_to_it(self):
        response = self.client.get(reverse("account_home"))
        self.assertContains(response, self.url)
        self.assertContains(response, "Change answers")
        questions.add_question(self.event, "Lunch?")
        response = self.client.get(reverse("account_home"))
        self.assertContains(response, "Answer the new question")
        child_page = self.client.get(reverse("ninja_detail", kwargs={"ninja_id": self.emma.id}))
        self.assertContains(child_page, self.url)
