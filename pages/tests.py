import re

from django.conf import settings
from django.contrib.gis.geos import MultiPolygon, Polygon
from django.core.cache import cache
from django.test import SimpleTestCase, TestCase
from django.urls import reverse
from django.utils import timezone

from content.models import Testimonial
from dojos.models import Dojo
from dojos.testing import make_champion, make_dojo
from pathways.models import Pathway


class HomeViewTests(TestCase):
    def setUp(self):
        # home() caches pathways/team/faqs (pages/views.py) — the test DB
        # resets between tests, but the cache doesn't, so a stale hit from
        # an earlier test/run would otherwise leak in here.
        cache.clear()

    def test_empty_site_renders(self):
        """The homepage composes widgets from several apps — none of them
        should assume there's at least one row to work with."""
        response = self.client.get(reverse("home"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "pages/home.html")

    def test_populated_site_renders(self):
        Pathway.objects.create(name="Scratch")
        Dojo.objects.create(name="Ghent")
        Testimonial.objects.create(quote="Great!", author="A parent")

        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["pathways"]), 1)
        self.assertIsNotNone(response.context["testimonial"])


class DataCacheTests(TestCase):
    """core.caching and the public pages' query counts (CAPACITY.md,
    "Caching"). The counts are guards: a change that adds queries to these
    pages should be a decision, so update them only on purpose."""

    def setUp(self):
        cache.clear()

    def test_a_value_is_built_once_and_cleared_when_a_row_changes(self):
        from content.models import Sponsor
        from core.caching import cached, clear_on_change

        built = []

        def build():
            built.append(1)
            return list(Sponsor.objects.values_list("name", flat=True))

        clear_on_change(["test:sponsors"], Sponsor)
        self.assertEqual(cached("test:sponsors", build, 60), [])
        self.assertEqual(cached("test:sponsors", build, 60), [])
        self.assertEqual(len(built), 1)
        Sponsor.objects.create(name="Acme")
        self.assertEqual(cached("test:sponsors", build, 60), ["Acme"])
        self.assertEqual(len(built), 2)

    def test_a_cached_none_is_a_hit(self):
        from core.caching import cached

        built = []
        cached("test:none", lambda: built.append(1), 60)
        cached("test:none", lambda: built.append(1), 60)
        self.assertEqual(len(built), 1)

    def test_the_home_page_shows_a_new_sponsor_and_testimonial_at_once(self):
        from content.models import Sponsor

        self.client.get(reverse("home"))
        Sponsor.objects.create(name="Acme")
        Testimonial.objects.create(quote="Great!", author="A parent")
        response = self.client.get(reverse("home"))
        self.assertEqual([s.name for s in response.context["sponsors"]], ["Acme"])
        self.assertEqual(response.context["testimonial"].quote, "Great!")

    def _warm_queries(self, url):
        """Queries of the second visit, once the caches are filled."""
        from core.testing import site_queries

        self.client.get(url)
        with site_queries() as queries:
            self.assertEqual(self.client.get(url).status_code, 200)
        return len(queries)

    def test_the_public_pages_read_their_content_from_the_cache(self):
        from datetime import timedelta

        from events.models import Event

        dojo = make_dojo("Ghent", champion=make_champion())
        start = timezone.now() + timedelta(days=3)
        for n in range(5):
            Event.objects.create(
                name=f"Session {n}",
                dojo=dojo,
                status=Event.OPEN,
                places=10,
                start_time=start,
                end_time=start + timedelta(hours=2),
            )
        # The home page's one query is the dojo finder widget's next sessions;
        # the dojo page's is its next session (its places change with every
        # booking).
        self.assertEqual(self._warm_queries(reverse("home")), 1)
        self.assertEqual(self._warm_queries(reverse("event_list")), 1)
        self.assertEqual(self._warm_queries(reverse("dojo_list")), 1)
        self.assertEqual(self._warm_queries(reverse("dojo_detail", args=[dojo.id])), 1)


class ProxyErrorPageTests(TestCase):
    """The proxy's own page when the site can't answer (.devcontainer/nginx/
    errors/busy.html, nginx.conf's error_page): it's served while Django is
    down or refusing requests, so it must stand on its own."""

    def setUp(self):
        root = settings.BASE_DIR / ".devcontainer" / "nginx"
        self.page = (root / "errors" / "busy.html").read_text()
        self.conf = (root / "nginx.conf").read_text()

    def test_it_needs_nothing_but_itself(self):
        self.assertNotIn("<script", self.page.lower())
        self.assertNotIn("<link", self.page.lower())
        # Nothing from another site; only the site's own fonts, from /static/.
        self.assertEqual(re.findall(r"https?://", self.page), [])
        for url in re.findall(r'url\("([^"]+)"\)', self.page):
            self.assertTrue(url.startswith("/static/core/fonts/"), url)

    def test_it_speaks_the_sites_three_languages(self):
        for language in ("nl", "fr", "en"):
            self.assertIn(f'<section lang="{language}">', self.page)

    def test_nginx_serves_it_for_the_sites_own_failures_only(self):
        self.assertIn("error_page 502 503 504 /_errors/busy.html;", self.conf)
        self.assertIn("proxy_intercept_errors on;", self.conf)
        # The uptime check and the API keep their own answers.
        for location in ("location = /health/ {", "location /api/ {"):
            block = self.conf.split(location, 1)[1].split("}", 1)[0]
            self.assertNotIn("proxy_intercept_errors", block)


class DevMonitoringTests(SimpleTestCase):
    """Prometheus and Grafana in the devcontainer (the `monitoring` profile):
    off unless asked for, scraping /metrics/ with the workspace's own token,
    and reachable through nginx."""

    def setUp(self):
        root = settings.BASE_DIR / ".devcontainer"
        self.compose = (root / "docker-compose.yml").read_text()
        self.prometheus = (root / "monitoring" / "prometheus.yml").read_text()
        self.conf = (root / "nginx" / "nginx.conf").read_text()

    def test_both_are_behind_the_profile(self):
        for service in ("prometheus", "grafana"):
            block = re.split(r"\n  \S", self.compose.split(f"\n  {service}:\n", 1)[1], maxsplit=1)[0]
            self.assertIn("profiles: [monitoring]", block, service)

    def test_prometheus_sends_the_workspaces_token(self):
        token = re.search(r"METRICS_TOKEN: (\S+)", self.compose).group(1)
        self.assertIn(f"credentials: {token}", self.prometheus)
        self.assertIn('targets: ["workspace:8000"]', self.prometheus)
        self.assertRegex(self.compose, r"ALLOWED_HOSTS: .*\bworkspace\b")

    def test_nginx_proxies_both_and_explains_when_they_are_off(self):
        for path in ("/prometheus/", "/grafana/"):
            block = self.conf.split(f"location {path} {{", 1)[1].split("}", 1)[0]
            self.assertIn("@monitoring_off", block)


class SeedContentLanguagesTests(TestCase):
    """manage.py seed_content_languages: realistic languages per region and
    the seeded texts in them; rerun-safe."""

    def test_languages_by_region(self):
        from geo.models import AdministrativeBoundary
        from pages.management.commands.seed_content_languages import seeded_languages

        def province(name):
            return AdministrativeBoundary.objects.create(
                name=name,
                kind=AdministrativeBoundary.PROVINCE,
                boundary=MultiPolygon(Polygon(((4, 50), (5, 50), (5, 51), (4, 50)))),
            )

        walloon, flemish = province("Province de Namur"), province("Provincie Limburg")
        for i in range(12):
            wallonia = seeded_languages(make_dojo(f"W{i}", province=walloon), km_from_brussels=60)
            self.assertEqual(wallonia[0], "fr-be")
            self.assertIn(wallonia, (["fr-be"], ["fr-be", "en-us"]))
            flanders = seeded_languages(make_dojo(f"F{i}", province=flemish), km_from_brussels=80)
            self.assertIn(flanders, (["nl-be"], ["nl-be", "en-us"], ["nl-be", "fr-be"]))
        near = seeded_languages(make_dojo("Near", province=flemish), km_from_brussels=8)
        self.assertEqual(near, ["nl-be", "fr-be", "en-us"])

    def test_texts_in_the_dojo_languages_and_rerun_safe(self):
        from io import StringIO

        from django.core.management import call_command

        from content.models import FAQ
        from events.management.commands.seed_events import description_for
        from events.models import Event

        dojo = make_dojo(
            "Namur",
            languages=["fr-be", "en-us"],
            tagline="Seeing a kid's face light up when their code finally runs — that's the whole job.",
        )
        faq = FAQ.objects.create(
            dojo=dojo,
            question="Is there parking nearby?",
            answer="Yes, free parking is available right outside the venue.",
        )
        global_faq = FAQ.objects.create(
            question="Is it really free?", answer="Yes — every Dojo session is free, run entirely by volunteers."
        )
        event = Event.objects.create(
            dojo=dojo,
            name="Coding Saturday",
            description=description_for("Coding Saturday"),
            start_time=timezone.now(),
            end_time=timezone.now(),
            places=5,
        )
        pathway = Pathway.objects.create(name="Web Development", subtitle="x")

        call_command("seed_content_languages", stdout=StringIO())
        for obj in (dojo, faq, global_faq, event, pathway):
            obj.refresh_from_db()
        self.assertTrue(dojo.tagline.startswith("Voir le visage"))
        self.assertTrue(dojo.translation_for("en-us", "tagline").startswith("Seeing a kid"))
        self.assertEqual(faq.question, "Y a-t-il un parking à proximité ?")
        self.assertEqual(faq.translation_for("nl-be", "question"), "")
        self.assertEqual(global_faq.question, "Is it really free?")
        self.assertEqual(global_faq.translation_for("nl-be", "question"), "Is het echt gratis?")
        self.assertEqual(event.name, "Samedi code")
        self.assertIn("**Samedi code**", event.description)
        self.assertEqual(pathway.translation_for("fr-be", "name"), "Développement web")

        out = StringIO()
        call_command("seed_content_languages", stdout=out)
        self.assertNotRegex(out.getvalue(), r"=[1-9]")


class ContactAndCodeOfConductTests(TestCase):
    """The footer's contact details (settings.ORGANISATION_CONTACT) and its
    Contact and Code of conduct pages."""

    def test_footer_shows_the_organisation_and_links_the_pages(self):
        response = self.client.get(reverse("home"))
        self.assertContains(response, 'href="mailto:info@coderdojobelgium.be"')
        self.assertContains(response, "Liersesteenweg 4, 2800 Mechelen")
        self.assertContains(response, f'href="{reverse("contact")}"')
        self.assertContains(response, f'href="{reverse("code_of_conduct")}"')

    def test_contact_page(self):
        response = self.client.get(reverse("contact"))
        self.assertContains(response, "0523.889.476")
        self.assertContains(response, "https://www.instagram.com/coderdojobelgium/")

    def test_code_of_conduct_in_the_visitors_language(self):
        self.assertContains(self.client.get(reverse("code_of_conduct")), "call 112")
        self.assertContains(self.client.get(reverse("code_of_conduct"), HTTP_ACCEPT_LANGUAGE="nl-be"), "Gedragscode")


class HealthCheckTests(TestCase):
    """/health/ for uptime monitoring (pages/health.py): 200 while the
    database, Redis and the mail workers are fine, 503 naming the failed check."""

    def test_healthy_site_answers_ok_to_anyone(self):
        response = self.client.get(reverse("health"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(), {"status": "ok", "checks": {"database": "ok", "redis": "ok", "mail_workers": "ok"}}
        )
        self.assertIn("no-cache", response["Cache-Control"])

    def test_redis_down_is_503(self):
        from unittest import mock

        with (
            mock.patch("pages.health.get_redis_connection", side_effect=ConnectionError("down")),
            self.assertLogs("pages.health", "ERROR"),
        ):
            response = self.client.get(reverse("health"))
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["status"], "error")
        self.assertEqual(response.json()["checks"]["redis"], "error")
        self.assertEqual(response.json()["checks"]["database"], "ok")

    def test_mail_waiting_too_long_means_the_workers_are_down(self):
        from datetime import timedelta

        from mailing.categories import MailCategory
        from mailing.models import EmailMessage

        mail = EmailMessage.objects.create(
            category=MailCategory.SERVICE,
            recipient="a@example.com",
            subject="Hi",
            body="…",
            send_after=timezone.now() - timedelta(minutes=10),
        )
        self.assertEqual(self.client.get(reverse("health")).status_code, 200)

        mail.send_after = timezone.now() - timedelta(hours=1)
        mail.save()
        with self.assertLogs("pages.health", "ERROR"):
            response = self.client.get(reverse("health"))
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["checks"]["mail_workers"], "error")

    def test_only_get(self):
        self.assertEqual(self.client.post(reverse("health")).status_code, 405)


class ManagementAreaTests(TestCase):
    """One management area for the organisation and its dojos (DATA_MODEL.md
    §20): one entry point (/manage/), one sidebar with a switcher between
    what the account can manage, and the organisation's events next to their
    promotions. Only the navigation is shared: the organisation's pages still
    need the admin role, a dojo (an organisation dojo too) a membership and a
    valid background check."""

    def setUp(self):
        from datetime import timedelta

        from accounts.models import OrganisationRole
        from dojos.testing import add_member, make_champion, make_mentor
        from events.models import Event

        self.OrganisationRole = OrganisationRole
        self.org_dojo = make_dojo(
            "CoderDojo Belgium", champion=make_champion(username="orgchamp"), kind=Dojo.ORGANISATION
        )
        self.ghent = make_dojo("Ghent", champion=make_champion(username="ghentchamp"))
        # An organisation admin with a valid check, mentor on the organisation dojo's team and at Ghent.
        self.staff = make_mentor(username="staff")
        OrganisationRole.objects.create(account=self.staff, role=OrganisationRole.ADMIN)
        add_member(self.org_dojo, self.staff)
        add_member(self.ghent, self.staff)
        start = timezone.now() + timedelta(days=14)
        self.event = Event.objects.create(
            name="CoderDojo Girlz",
            dojo=self.org_dojo,
            status=Event.OPEN,
            places=10,
            start_time=start,
            end_time=start + timedelta(hours=4),
        )

    def _admin_without_check(self):
        from accounts.models import User

        user = User.objects.create(username="nocheck", email="nocheck@example.com")
        self.OrganisationRole.objects.create(account=user, role=self.OrganisationRole.ADMIN)
        return user

    def _dashboard(self, dojo):
        return reverse("dojo_dashboard", kwargs={"dojo_id": dojo.id})

    # the switcher

    def test_the_switcher_lists_the_organisation_its_events_and_the_dojos(self):
        self.client.force_login(self.staff)
        for url in (reverse("manage_campaign_list"), self._dashboard(self.ghent)):
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertContains(response, "data-cd-adminnav-switcher")
                self.assertContains(response, f'href="{reverse("manage_home")}"')
                self.assertContains(response, "Organisation events")
                self.assertContains(response, "Your dojos")
                self.assertContains(response, self._dashboard(self.org_dojo))
                self.assertContains(response, self._dashboard(self.ghent))

    def test_a_mentor_never_sees_the_organisation(self):
        from dojos.testing import add_member, make_mentor

        mentor = make_mentor(username="mentor")
        add_member(self.ghent, mentor)
        self.client.force_login(mentor)
        response = self.client.get(self._dashboard(self.ghent))
        self.assertNotContains(response, "data-cd-adminnav-switcher")  # one dojo: nothing to switch to
        self.assertNotContains(response, f'href="{reverse("manage_home")}"')
        self.assertEqual(self.client.get(reverse("manage_campaign_list")).status_code, 404)

    def test_an_organisation_admin_without_a_background_check_sees_no_dojos(self):
        """Not everyone in the organisation needs a check: without one, the
        organisation's pages only, and a dojo is a 404, even on its team."""
        from dojos.testing import add_member

        admin = self._admin_without_check()
        add_member(self.org_dojo, admin)
        self.client.force_login(admin)
        response = self.client.get(reverse("manage_campaign_list"))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "data-cd-adminnav-switcher")
        self.assertNotContains(response, "Organisation events")
        self.assertNotContains(response, self._dashboard(self.org_dojo))
        self.assertEqual(self.client.get(self._dashboard(self.org_dojo)).status_code, 404)

    def test_a_lapsed_check_takes_the_dojos_away_but_not_the_organisation(self):
        from datetime import timedelta

        self.staff.background_check_expires_at = timezone.now() - timedelta(days=1)
        self.staff.save(update_fields=["background_check_expires_at"])
        self.client.force_login(self.staff)
        response = self.client.get(reverse("manage_campaign_list"))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "data-cd-adminnav-switcher")
        self.assertNotContains(response, self._dashboard(self.ghent))

    def test_the_organisation_sidebar_links_its_events(self):
        self.client.force_login(self.staff)
        response = self.client.get(reverse("manage_campaign_list"))
        self.assertContains(response, f'href="{reverse("dojo_event_list", kwargs={"dojo_id": self.org_dojo.id})}"')

    # one entry point

    def test_manage_opens_the_organisation_else_the_first_dojo(self):
        from accounts.models import User

        self.client.force_login(self.staff)
        self.assertRedirects(self.client.get(reverse("manage_home")), reverse("manage_campaign_list"))
        self.client.force_login(User.objects.get(username="ghentchamp"))
        self.assertRedirects(self.client.get(reverse("manage_home")), self._dashboard(self.ghent))

    def test_manage_is_a_404_for_anyone_else(self):
        from accounts.models import User

        self.client.force_login(User.objects.create(username="parent"))
        self.assertEqual(self.client.get(reverse("manage_home")).status_code, 404)
        self.client.logout()
        self.assertEqual(self.client.get(reverse("manage_home")).status_code, 302)  # to login

    def test_one_manage_link_and_login_goes_there(self):
        self.client.force_login(self.staff)
        response = self.client.get(reverse("home"))
        self.assertContains(response, f'href="{reverse("manage_home")}"', count=1)
        self.assertNotContains(response, 'href="/admin/"')
        self.assertRedirects(self.client.get(reverse("login")), reverse("manage_home"), target_status_code=302)

    def test_an_organisation_admin_without_a_dojo_lands_in_the_organisation(self):
        self.client.force_login(self._admin_without_check())
        self.assertRedirects(self.client.get(reverse("login")), reverse("manage_home"), target_status_code=302)

    # promotions next to the event

    def _event_page(self):
        return reverse("dojo_event_detail", kwargs={"dojo_id": self.org_dojo.id, "event_id": self.event.id})

    def test_the_event_page_shows_its_promotions_to_an_organisation_admin(self):
        from content.models import Promotion

        promotion = Promotion.objects.create(event=self.event, placement=Promotion.HOMEPAGE_HERO)
        self.client.force_login(self.staff)
        response = self.client.get(self._event_page())
        self.assertContains(response, "Promote this event")
        self.assertContains(response, f"{reverse('manage_promotion_create')}?event={self.event.id}")
        self.assertContains(response, reverse("manage_promotion_detail", kwargs={"promotion_id": promotion.id}))
        self.assertContains(response, "Showing")

    def test_the_team_without_the_organisation_role_sees_no_promotions(self):
        from accounts.models import User

        self.client.force_login(User.objects.get(username="orgchamp"))
        response = self.client.get(self._event_page())
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Promote this event")
        self.assertNotContains(response, 'class="cd-card event-promotions-card"')

    def test_an_ended_event_can_no_longer_be_promoted(self):
        from datetime import timedelta

        self.event.start_time = timezone.now() - timedelta(days=2)
        self.event.end_time = self.event.start_time + timedelta(hours=4)
        self.event.save()
        self.client.force_login(self.staff)
        response = self.client.get(self._event_page())
        self.assertContains(response, 'class="cd-card event-promotions-card"')
        self.assertNotContains(response, "Promote this event")

    def test_promote_this_event_fills_in_the_event(self):
        self.client.force_login(self.staff)
        response = self.client.get(f"{reverse('manage_promotion_create')}?event={self.event.id}")
        self.assertEqual(str(response.context["form"]["event"].value()), str(self.event.id))

    def test_the_promotions_list_links_events_the_account_manages(self):
        from content.models import Promotion
        from events.models import Event

        other = make_dojo("Antwerp")
        other_event = Event.objects.create(
            name="Other",
            dojo=other,
            status=Event.OPEN,
            places=5,
            start_time=self.event.start_time,
            end_time=self.event.end_time,
        )
        Promotion.objects.create(event=self.event, placement=Promotion.HOMEPAGE_HERO)
        Promotion.objects.create(event=other_event, placement=Promotion.EVENT_LIST_TOP)
        self.client.force_login(self.staff)
        response = self.client.get(reverse("manage_promotion_list"))
        self.assertContains(response, self._event_page())
        self.assertNotContains(
            response, reverse("dojo_event_detail", kwargs={"dojo_id": other.id, "event_id": other_event.id})
        )
        self.assertNotContains(response, "you need a valid background check")

    def test_the_promotions_list_says_how_to_plan_organisation_events(self):
        self.client.force_login(self._admin_without_check())
        self.assertContains(self.client.get(reverse("manage_promotion_list")), "you need a valid background check")


class OrganisationAreaTests(TestCase):
    """The organisation dashboard's areas (DATA_MODEL.md §23): each group of
    its sidebar is a permission (accounts.organisation.AREA_PERMISSIONS),
    held through the role groups or granted by hand, and checked by every
    page (require_area), the sidebar and /manage/'s landing."""

    def setUp(self):
        from pages.manage import AREA_LANDINGS

        self.landings = {area: reverse(name) for area, name in AREA_LANDINGS.items()}

    def _account(self, username, *areas, role=None, **fields):
        from django.contrib.auth.models import Permission

        from accounts.models import OrganisationRole, User
        from accounts.organisation import AREA_PERMISSIONS

        user = User.objects.create(username=username, email=f"{username}@example.com", **fields)
        for area in areas:
            app_label, codename = AREA_PERMISSIONS[area].split(".")
            user.user_permissions.add(Permission.objects.get(content_type__app_label=app_label, codename=codename))
        if role:
            OrganisationRole.objects.create(account=user, role=role)
        return User.objects.get(pk=user.pk)  # a fresh permission cache

    def test_each_role_opens_its_areas(self):
        from accounts.models import OrganisationRole
        from accounts.organisation import Area, areas_of

        admin = self._account("admin", role=OrganisationRole.ADMIN)
        reviewer = self._account("reviewer", role=OrganisationRole.REVIEWER)
        board = self._account("board", role=OrganisationRole.BOARD)
        self.assertEqual(
            areas_of(admin),
            [
                Area.COMMUNICATION,
                Area.PUBLIC_SITE,
                Area.NINJAS,
                Area.PRIVACY,
                Area.SECURITY,
                Area.PEOPLE,
                Area.AUDIT_LOG,
            ],
        )
        self.assertEqual(areas_of(reviewer), [Area.VOLUNTEERS])
        self.assertEqual(areas_of(board), [])

    def test_each_page_needs_its_own_area(self):
        for area, url in self.landings.items():
            with self.subTest(area=area):
                self.client.force_login(self._account(f"only-{area}", area))
                self.assertEqual(self.client.get(url).status_code, 200)
                for other, other_url in self.landings.items():
                    if other != area:
                        self.assertEqual(self.client.get(other_url).status_code, 404, other)

    def test_manage_opens_the_first_area_the_account_has(self):
        from accounts.organisation import Area

        for areas, landing in (
            ((Area.SECURITY,), Area.SECURITY),
            ((Area.PRIVACY, Area.NINJAS), Area.NINJAS),
            ((Area.VOLUNTEERS, Area.COMMUNICATION), Area.COMMUNICATION),
        ):
            with self.subTest(areas=areas):
                self.client.force_login(self._account("-".join(areas), *areas))
                self.assertRedirects(
                    self.client.get(reverse("manage_home")), self.landings[landing], fetch_redirect_response=False
                )

    def test_a_role_without_an_area_only_gets_the_django_admin_page(self):
        """The board has no area yet: /manage/ opens its page to ask for the
        Django admin (DATA_MODEL.md §23), and every area is a 404."""
        from accounts.models import OrganisationRole

        self.client.force_login(self._account("board", role=OrganisationRole.BOARD))
        self.assertRedirects(
            self.client.get(reverse("manage_home")), reverse("manage_admin_access"), fetch_redirect_response=False
        )
        self.assertEqual(self.client.get(reverse("manage_admin_access")).status_code, 200)
        for url in self.landings.values():
            self.assertEqual(self.client.get(url).status_code, 404, url)

    def test_the_sidebar_shows_only_the_groups_of_its_areas(self):
        from accounts.organisation import Area

        self.client.force_login(self._account("privacy", Area.PRIVACY))
        response = self.client.get(self.landings[Area.PRIVACY])
        self.assertContains(response, "Accounts")
        self.assertContains(response, f'href="{self.landings[Area.PRIVACY]}"')
        for area in (Area.COMMUNICATION, Area.VOLUNTEERS, Area.PUBLIC_SITE, Area.NINJAS, Area.SECURITY):
            self.assertNotContains(response, f'href="{self.landings[area]}"')
        self.assertNotContains(response, reverse("manage_campaign_create"))

    def test_a_superuser_opens_every_area(self):
        root = self._account("root", is_superuser=True, is_staff=True)
        self.client.force_login(root)
        for url in self.landings.values():
            self.assertEqual(self.client.get(url).status_code, 200, url)


class AuditLogPageTests(TestCase):
    """The audit log on the organisation dashboard (/manage/audit-log/,
    pages.audit_views, DATA_MODEL.md §14): read-only, for the organisation's
    admin role, with health, criminal-record and security values hidden."""

    def setUp(self):
        from accounts.models import OrganisationRole, User

        self.admin = User.objects.create(username="orgadmin", email="ann@example.com")
        OrganisationRole.objects.create(account=self.admin, role=OrganisationRole.ADMIN)
        self.url = reverse("manage_audit_log")
        self.client.force_login(self.admin)

    def _ninja(self, **fields):
        from accounts.models import Ninja

        return Ninja.objects.create(name="Lotte", family_name="Peeters", **fields)

    def test_only_the_admin_role_gets_in(self):
        from accounts.models import OrganisationRole, User

        self.client.logout()
        self.assertEqual(self.client.get(self.url).status_code, 302)  # to login
        for role in (OrganisationRole.BOARD, OrganisationRole.REVIEWER):
            other = User.objects.create(username=role, email=f"{role}@example.com")
            OrganisationRole.objects.create(account=other, role=role)
            self.client.force_login(other)
            self.assertEqual(self.client.get(self.url).status_code, 404, role)
        self.client.force_login(self.admin)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "pages/manage_audit_log.html")
        self.assertContains(response, f'href="{self.url}"')  # the sidebar link

    def test_it_is_read_only(self):
        self.assertEqual(self.client.post(self.url).status_code, 405)

    def test_ordinary_changes_are_shown(self):
        ninja = self._ninja()
        ninja.name = "Lotte-Marie"
        ninja.save()
        response = self.client.get(self.url)
        self.assertContains(response, "Lotte-Marie")
        self.assertContains(response, "Lotte</span> → <span>Lotte-Marie")

    def test_health_criminal_and_security_values_are_hidden(self):
        from accounts.models import User

        ninja = self._ninja(allergies_notes="Peanut allergy")
        ninja.allergies_notes = "Peanut and egg allergy"
        ninja.save()
        volunteer = User.objects.create(username="vol", email="vol@example.com")
        volunteer.background_check_status = User.CHECK_REJECTED
        volunteer.set_password("s3cret-Password")
        volunteer.save()

        response = self.client.get(self.url)
        content = response.content.decode()
        for value in ("Peanut", "rejected", "Rejected", "pbkdf2", "s3cret"):
            self.assertNotIn(value, content)
        self.assertIn("****", content)
        by_field = {
            change["field"].lower(): change for _, _, changes in response.context["rows"] for change in changes
        }
        for field in ("allergies notes", "background check status", "password"):
            self.assertTrue(by_field[field.lower()]["hidden"], field)
        self.assertFalse(by_field["email address"]["hidden"])

    def test_a_field_without_a_privacy_decision_is_hidden(self):
        from accounts.models import Ninja
        from core.audit import is_hidden

        self.assertTrue(is_hidden(Ninja, "no_such_field"))
        self.assertTrue(is_hidden(None, "name"))
        self.assertFalse(is_hidden(Ninja, "name"))
        self.assertTrue(is_hidden(Ninja, "allergies_notes"))
        # Who did something stays visible, though it's kept out of an export.
        from accounts.models import AdminAccessGrant

        self.assertFalse(is_hidden(AdminAccessGrant, "ended_by"))

    def test_filters(self):
        from auditlog.models import LogEntry
        from django.contrib.contenttypes.models import ContentType

        from accounts.models import Ninja

        ninja = self._ninja()
        make_dojo("Dojo Gent")
        ninja.delete()

        response = self.client.get(self.url, {"q": "Gent"})
        found = [entry.object_repr for entry, _, _ in response.context["rows"]]
        self.assertTrue(found)
        self.assertTrue(all("Gent" in repr_ for repr_ in found), found)
        response = self.client.get(self.url, {"action": LogEntry.Action.DELETE})
        self.assertEqual([entry.action for entry, _, _ in response.context["rows"]], [LogEntry.Action.DELETE])
        response = self.client.get(self.url, {"type": ContentType.objects.get_for_model(Ninja).pk})
        self.assertTrue(response.context["rows"])
        self.assertTrue(all(entry.content_type.model == "ninja" for entry, _, _ in response.context["rows"]))
        # Nonsense filters are ignored, not errors.
        self.assertEqual(self.client.get(self.url, {"action": "x", "type": "999999", "page": "abc"}).status_code, 200)

    def test_pages(self):
        from auditlog.models import LogEntry

        from . import audit_views

        for _number in range(audit_views.PAGE_SIZE + 5):
            self._ninja()
        response = self.client.get(self.url)
        self.assertEqual(len(response.context["rows"]), audit_views.PAGE_SIZE)
        self.assertContains(response, "page=2")
        on_page_two = LogEntry.objects.count() - audit_views.PAGE_SIZE
        self.assertEqual(
            len(self.client.get(self.url, {"page": 2}).context["rows"]), min(on_page_two, audit_views.PAGE_SIZE)
        )


class AdminLoginWithoutAccessTests(TestCase):
    """A logged-in account without an open admin grant used to loop between the
    admin's login and the site's (which sends a logged-in account on to `next`)."""

    def setUp(self):
        from accounts.models import OrganisationRole, User

        self.admin = User.objects.create(username="orgadmin-noaccess")
        OrganisationRole.objects.create(account=self.admin, role=OrganisationRole.ADMIN)
        self.parent = User.objects.create(username="parent-noaccess")

    def admin_login(self):
        url = reverse("admin:index")
        return self.client.get(reverse("admin:login") + f"?next={url}")

    def test_an_organisation_role_is_sent_to_ask_for_access(self):
        self.client.force_login(self.admin)
        self.assertRedirects(
            self.client.get(reverse("admin:index")),
            reverse("admin:login") + "?next=/admin/",
            fetch_redirect_response=False,
        )
        self.assertRedirects(self.admin_login(), reverse("manage_admin_access"), fetch_redirect_response=False)

    def test_an_account_without_a_role_is_refused(self):
        self.client.force_login(self.parent)
        self.assertEqual(self.admin_login().status_code, 403)

    def test_someone_not_logged_in_goes_to_the_sites_login(self):
        response = self.admin_login()
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response["Location"].startswith(reverse("login")))

    def test_with_an_open_grant_the_admin_opens(self):
        from accounts.testing import with_admin_access

        self.client.force_login(with_admin_access(self.admin))
        self.assertEqual(self.client.get(reverse("admin:index")).status_code, 200)
