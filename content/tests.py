from datetime import timedelta
from io import StringIO

from django.core.cache import cache
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import OrganisationRole, User
from dojos.models import Dojo
from dojos.testing import make_dojo
from events.models import Event

from .models import Announcement, Promotion


class SeedAnnouncementsTests(TestCase):
    def test_seeds_dojos_without_updates_and_is_rerun_safe(self):
        dojos = [make_dojo(f"Dojo {n}") for n in range(8)]
        kept = dojos[0]
        Announcement.objects.create(dojo=kept, date="2026-01-01", text="Hand-written")

        call_command("seed_announcements", stdout=StringIO())
        count = Announcement.objects.count()
        call_command("seed_announcements", stdout=StringIO())

        self.assertGreater(count, 1)
        self.assertEqual(Announcement.objects.count(), count)
        self.assertEqual(list(kept.announcements.values_list("text", flat=True)), ["Hand-written"])
        self.assertFalse(Announcement.objects.filter(text__contains="{dojo}").exists())


def _event(dojo, days=14, **fields):
    start = timezone.now() + timedelta(days=days)
    return Event.objects.create(**{
        "name": "Coolest Projects", "dojo": dojo, "status": Event.OPEN, "places": 10,
        "start_time": start, "end_time": start + timedelta(hours=6), **fields,
    })


class PromotionShowingTests(TestCase):
    def setUp(self):
        self.org = make_dojo("CoderDojo Belgium", kind=Dojo.ORGANISATION)
        self.event = _event(self.org)
        self.now = timezone.now()

    def _showing(self, placement=Promotion.HOMEPAGE_HERO, now=None):
        return list(Promotion.objects.showing(placement, now=now or self.now))

    def test_shows_from_start_until_the_event_starts(self):
        promotion = Promotion.objects.create(event=self.event, placement=Promotion.HOMEPAGE_HERO,
                                             starts_at=self.now - timedelta(days=1))
        self.assertEqual(self._showing(), [promotion])
        self.assertEqual(self._showing(Promotion.EVENT_LIST_TOP), [])
        self.assertEqual(self._showing(now=self.now - timedelta(days=2)), [])  # not started yet
        self.assertEqual(self._showing(now=self.event.start_time + timedelta(minutes=1)), [])  # event started

    def test_an_explicit_end_wins(self):
        Promotion.objects.create(event=self.event, placement=Promotion.HOMEPAGE_HERO,
                                 starts_at=self.now - timedelta(days=2), ends_at=self.now - timedelta(days=1))
        self.assertEqual(self._showing(), [])

    def test_never_after_the_event_has_ended(self):
        Promotion.objects.create(event=self.event, placement=Promotion.HOMEPAGE_HERO,
                                 starts_at=self.now - timedelta(days=1), ends_at=self.now + timedelta(days=60))
        self.assertEqual(self._showing(now=self.event.end_time + timedelta(minutes=1)), [])

    def test_only_for_events_the_public_site_shows(self):
        Promotion.objects.create(event=_event(self.org, status=Event.DRAFT), placement=Promotion.HOMEPAGE_HERO,
                                 starts_at=self.now - timedelta(days=1))
        dormant = make_dojo("Sleepy", status=Dojo.DORMANT)
        Promotion.objects.create(event=_event(dormant), placement=Promotion.HOMEPAGE_HERO,
                                 starts_at=self.now - timedelta(days=1))
        self.assertEqual(self._showing(), [])

    def test_ordered_by_rank(self):
        second = Promotion.objects.create(event=self.event, placement=Promotion.HOMEPAGE_HERO, rank=2,
                                          starts_at=self.now - timedelta(days=1))
        first = Promotion.objects.create(event=_event(self.org, name="Girlz"), placement=Promotion.HOMEPAGE_HERO,
                                         rank=1, starts_at=self.now - timedelta(days=1))
        self.assertEqual(self._showing(), [first, second])

    def test_end_must_follow_start(self):
        from django.core.exceptions import ValidationError

        promotion = Promotion(event=self.event, placement=Promotion.HOMEPAGE_HERO,
                              starts_at=self.now, ends_at=self.now - timedelta(hours=1))
        with self.assertRaises(ValidationError):
            promotion.full_clean()


class PromotionPlacementTests(TestCase):
    """Each placement shows up where it belongs on the public site."""

    def setUp(self):
        cache.clear()
        self.org = make_dojo("CoderDojo Belgium", kind=Dojo.ORGANISATION)
        self.dojo = make_dojo("Ghent")
        self.soon = _event(self.dojo, days=3, name="Coding Saturday")
        self.featured = _event(self.org, days=40, name="Coolest Projects")

    def _promote(self, placement, **fields):
        return Promotion.objects.create(event=self.featured, placement=placement,
                                        starts_at=timezone.now() - timedelta(hours=1), **fields)

    def test_homepage_hero(self):
        self._promote(Promotion.HOMEPAGE_HERO, title="Show what you made", text="Sign up your project!")
        response = self.client.get(reverse("home"))
        self.assertContains(response, "cd-promo--hero")
        self.assertContains(response, "Show what you made")
        self.assertContains(response, "Sign up your project!")
        self.assertContains(response, "Organised by CoderDojo Belgium")

    def test_nothing_promoted_shows_nothing(self):
        for url in (reverse("home"), reverse("event_list"), reverse("dojo_list")):
            self.assertNotContains(self.client.get(url), "cd-promo")

    def test_event_list_top_only_on_the_unfiltered_list(self):
        self._promote(Promotion.EVENT_LIST_TOP)
        self.assertContains(self.client.get(reverse("event_list")), "cd-promo--banner")
        self.assertNotContains(self.client.get(reverse("event_list"), {"date": "week"}), "cd-promo")

    def test_dojo_finder_banner(self):
        self._promote(Promotion.DOJO_FINDER_BANNER)
        self.assertContains(self.client.get(reverse("dojo_list")), "cd-promo--banner")
        self.assertContains(self.client.get(reverse("home")), "cd-promo--banner")

    def test_upcoming_first_puts_the_event_first_in_the_carousel(self):
        from events.search import upcoming_available_events

        self.assertEqual(upcoming_available_events()[0], self.soon)
        self._promote(Promotion.UPCOMING_FIRST)  # saving clears the carousel's cache
        events = upcoming_available_events()
        self.assertEqual(events[:2], [self.featured, self.soon])
        self.assertTrue(events[0].is_promoted)
        self.assertFalse(events[1].is_promoted)
        self.assertContains(self.client.get(reverse("home")), "Featured</span>")


class PromotionDashboardTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create(username="orgadmin", email="ann@example.com")
        OrganisationRole.objects.create(account=self.admin, role=OrganisationRole.ADMIN)
        self.org = make_dojo("CoderDojo Belgium", kind=Dojo.ORGANISATION)
        self.event = _event(self.org)
        self.client.force_login(self.admin)

    def test_only_the_organisation_admin_role_gets_in(self):
        promotion = Promotion.objects.create(event=self.event, placement=Promotion.HOMEPAGE_HERO)
        urls = [reverse("manage_promotion_list"), reverse("manage_promotion_create"),
                reverse("manage_promotion_detail", kwargs={"promotion_id": promotion.id})]
        self.client.logout()
        for url in urls:
            self.assertEqual(self.client.get(url).status_code, 302)  # to login
        board = User.objects.create(username="board", email="bo@example.com")
        OrganisationRole.objects.create(account=board, role=OrganisationRole.BOARD)
        for user in (board, User.objects.create(username="parent")):
            self.client.force_login(user)
            for url in urls:
                self.assertEqual(self.client.get(url).status_code, 404)
        delete = reverse("manage_promotion_delete", kwargs={"promotion_id": promotion.id})
        self.assertEqual(self.client.post(delete).status_code, 404)
        self.assertTrue(Promotion.objects.exists())

    def test_list_shows_each_placement_and_state(self):
        Promotion.objects.create(event=self.event, placement=Promotion.HOMEPAGE_HERO, title="Live one")
        Promotion.objects.create(event=_event(self.org, status=Event.DRAFT, name="Not yet"),
                                 placement=Promotion.EVENT_LIST_TOP)
        response = self.client.get(reverse("manage_promotion_list"))
        self.assertTemplateUsed(response, "content/manage/promotion_list.html")
        self.assertContains(response, "Live one")
        self.assertContains(response, "Showing")
        self.assertContains(response, "Event not public")
        self.assertContains(response, "Nothing promoted here.")  # the two empty placements

    def test_create(self):
        response = self.client.post(reverse("manage_promotion_create"), {
            "event": self.event.id, "placement": Promotion.UPCOMING_FIRST, "rank": "3",
            "starts_at": "2026-01-01T09:00", "ends_at": "", "title": "", "text": "Come along",
        })
        self.assertRedirects(response, reverse("manage_promotion_list"))
        promotion = Promotion.objects.get()
        self.assertEqual((promotion.event, promotion.placement, promotion.rank, promotion.text),
                         (self.event, Promotion.UPCOMING_FIRST, 3, "Come along"))
        self.assertIsNone(promotion.ends_at)

    def test_create_prefills_the_event(self):
        response = self.client.get(reverse("manage_promotion_create"), {"event": self.event.id})
        self.assertEqual(str(response.context["form"]["event"].value()), str(self.event.id))

    def test_past_events_are_not_offered(self):
        past = _event(self.org, days=-10, name="Over")
        response = self.client.get(reverse("manage_promotion_create"))
        self.assertNotIn(past, response.context["form"].fields["event"].queryset)
        self.assertIn(self.event, response.context["form"].fields["event"].queryset)

    def test_edit_and_invalid_window(self):
        promotion = Promotion.objects.create(event=self.event, placement=Promotion.HOMEPAGE_HERO)
        url = reverse("manage_promotion_detail", kwargs={"promotion_id": promotion.id})
        data = {"event": self.event.id, "placement": Promotion.HOMEPAGE_HERO, "rank": "0",
                "starts_at": "2026-01-02T09:00", "ends_at": "2026-01-01T09:00", "title": "", "text": ""}
        self.assertEqual(self.client.post(url, data).status_code, 200)
        data["ends_at"] = "2026-02-01T09:00"
        data["rank"] = "5"
        self.assertRedirects(self.client.post(url, data), reverse("manage_promotion_list"))
        promotion.refresh_from_db()
        self.assertEqual(promotion.rank, 5)

    def test_delete(self):
        promotion = Promotion.objects.create(event=self.event, placement=Promotion.HOMEPAGE_HERO)
        url = reverse("manage_promotion_delete", kwargs={"promotion_id": promotion.id})
        self.assertEqual(self.client.get(url).status_code, 405)
        self.assertRedirects(self.client.post(url), reverse("manage_promotion_list"))
        self.assertFalse(Promotion.objects.exists())


class SeedOrganisationTests(TestCase):
    def test_seeds_the_organisation_and_is_rerun_safe(self):
        call_command("seed_organisation", stdout=StringIO())
        call_command("seed_organisation", stdout=StringIO())
        org = Dojo.objects.get(kind=Dojo.ORGANISATION)
        self.assertEqual(org.status, Dojo.ACTIVE)
        self.assertIsNotNone(org.champion)
        self.assertEqual(org.event_set.count(), 2)
        self.assertTrue(org.event_set.exclude(external_registration_url="").exists())
        self.assertEqual(set(Promotion.objects.values_list("placement", flat=True)),
                         {value for value, _ in Promotion.PLACEMENT_CHOICES})
