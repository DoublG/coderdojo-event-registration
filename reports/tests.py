import json
from datetime import date

from django.core.cache import cache
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone, translation

from accounts.models import Ninja, OrganisationRole, User
from dojos.testing import make_dojo
from events.models import NinjaEngagement

from .config import ConfigError, parse, to_stored, to_viewer
from .datasets import DATASETS
from .datasets.base import OTHER, generalise, merge
from .datasets.engagement import EngagementDataset, age_band
from .models import Report


class DatasetPrivacyTests(SimpleTestCase):
    """Every column of every dataset comes from a field the privacy registry
    knows, and never from health, criminal-record or security data
    (DATA_MODEL_REPORTS.md §30): the rows reach the administrator's browser."""

    def test_every_column_is_a_classified_field_that_may_be_reported(self):
        from django.apps import apps

        from core.privacy_registry import Category, site

        forbidden = {Category.SPECIAL, Category.CRIMINAL, Category.SECURITY}
        for dataset in DATASETS.values():
            for column in dataset.columns:
                with self.subTest(dataset=dataset.key, column=column.key):
                    model = apps.get_model(column.source[0])
                    field = column.source[1]
                    model._meta.get_field(field)  # the field exists
                    entry = site.get(model)
                    self.assertIsNotNone(entry, f"{model._meta.label} isn't in the privacy registry")
                    if field in entry.not_personal:
                        continue
                    self.assertIn(field, entry.fields, f"{model._meta.label}.{field} has no classification")
                    self.assertNotIn(entry.fields[field].category, forbidden)

    def test_columns_have_unique_keys_and_labels(self):
        for dataset in DATASETS.values():
            keys = [column.key for column in dataset.columns]
            labels = [str(column.label) for column in dataset.columns]
            self.assertEqual(len(keys), len(set(keys)), dataset.key)
            self.assertEqual(len(labels), len(set(labels)), dataset.key)

    def test_children_datasets_generalise_known_dimensions(self):
        for dataset in DATASETS.values():
            if dataset.about_children:
                self.assertIn(dataset.count_column, dataset.measures)
                self.assertTrue(set(dataset.generalise_order) <= set(dataset.dimensions))


class GeneraliseTests(SimpleTestCase):
    DIMS = ["stage", "dojo"]

    def _rows(self, *rows):
        return [{"stage": stage, "dojo": dojo, "n": n} for stage, dojo, n in rows]

    def test_merge_adds_up_matching_rows(self):
        rows = merge(self._rows(("a", "x", 2), ("a", "x", 3), ("b", "x", 1)), self.DIMS, ["n"])
        self.assertEqual(sorted((r["stage"], r["n"]) for r in rows), [("a", 5), ("b", 1)])

    def test_small_groups_lose_their_most_identifying_dimension_first(self):
        rows = self._rows(("a", "x", 7), ("a", "y", 2), ("a", "z", 3), ("b", "x", 1))
        table = generalise(rows, self.DIMS, ["n"], "n", ["dojo", "stage"], 5)
        found = sorted((r["stage"], r["dojo"], r["n"]) for r in table.rows)
        # a/y and a/z merge into a/Other (5); b/x is still too small after
        # losing its dojo, and then its stage: left out.
        self.assertEqual(found, [("a", OTHER, 5), ("a", "x", 7)])
        self.assertEqual(table.hidden, 1)

    def test_totals_stay_right_when_nothing_is_left_out(self):
        rows = self._rows(("a", "x", 3), ("b", "y", 3))
        table = generalise(rows, self.DIMS, ["n"], "n", ["dojo", "stage"], 5)
        self.assertEqual(sum(r["n"] for r in table.rows), 6)
        self.assertEqual(table.hidden, 0)


class EngagementDatasetTests(TestCase):
    def setUp(self):
        self.dojo = make_dojo("Ghent")
        this_year = timezone.localdate().year
        for i in range(6):
            ninja = Ninja.objects.create(name=f"Kid {i}", date_of_birth=date(this_year - 10, 1, 1), gender="girl")
            NinjaEngagement.objects.create(
                ninja=ninja,
                main_dojo=self.dojo,
                stage=NinjaEngagement.REGULAR,
                attended_180d=4,
                offered_180d=5,
                computed_on=timezone.localdate(),
            )
        # A row per dojo is not the overall row: never counted.
        NinjaEngagement.objects.create(
            ninja=ninja, dojo=self.dojo, stage=NinjaEngagement.LAPSED, computed_on=timezone.localdate()
        )
        lone = Ninja.objects.create(name="Lone", date_of_birth=date(this_year - 15, 1, 1), gender="boy")
        NinjaEngagement.objects.create(
            ninja=lone, main_dojo=self.dojo, stage=NinjaEngagement.LAPSED, computed_on=timezone.localdate()
        )

    def test_age_bands(self):
        self.assertEqual(age_band(2016, 2026), "10-12")
        self.assertEqual(age_band(2008, 2026), "18+")
        self.assertIsNone(age_band(2022, 2026))
        self.assertIsNone(age_band(None, 2026))

    def test_overall_rows_only_with_small_groups_generalised(self):
        table = EngagementDataset().table(min_group=5)
        self.assertEqual(len(table.rows), 1)
        row = table.rows[0]
        self.assertEqual(
            (row["stage"], row["main_dojo"], row["age_band"], row["gender"]), ("regular", "Ghent", "10-12", "girl")
        )
        self.assertEqual((row["ninjas"], row["attended_180d"], row["offered_180d"]), (6, 24, 30))
        self.assertEqual(table.hidden, 1)  # the lone lapsed boy

    def test_rows_are_labelled_in_the_current_language(self):
        dataset = EngagementDataset()
        with translation.override("nl-be"):
            [row] = dataset.labelled(dataset.table(min_group=5))
        self.assertEqual(row["Betrokkenheidsfase"], "Vaste bezoeker")
        self.assertEqual(row["Kinderen"], 6)


class ConfigTests(SimpleTestCase):
    """A saved report doesn't depend on the language it was made in."""

    def setUp(self):
        self.dataset = EngagementDataset()

    def _viewer_config(self):
        return {
            "plugin": "Y Bar",
            "group_by": ["Province"],
            "split_by": ["Engagement stage"],
            "columns": ["Children", "ratio"],
            "filter": [["Engagement stage", "in", ["Regular", "Lapsed"]], ["Main dojo", "==", "Ghent"]],
            "sort": [["Children", "desc"]],
            "aggregates": {"Children": "sum"},
            "expressions": {"ratio": '"Sessions attended (180 days)" / "Sessions offered (180 days)"'},
            "theme": "Pro Dark",
            "title": "x",
            "table": "figures",
        }

    def test_stored_with_references_and_back_in_another_language(self):
        with translation.override("en-us"):
            stored = to_stored(self._viewer_config(), self.dataset)
        self.assertEqual(stored["group_by"], ["col:province"])
        self.assertEqual(stored["filter"][0], ["col:stage", "in", ["val:regular", "val:lapsed"]])
        self.assertEqual(stored["filter"][1], ["col:main_dojo", "==", "Ghent"])  # a name stays a name
        self.assertEqual(stored["aggregates"], {"col:ninjas": "sum"})
        self.assertIn('"col:attended_180d"', stored["expressions"]["ratio"])
        for key in ("theme", "title", "table"):
            self.assertNotIn(key, stored)
        with translation.override("nl-be"):
            config, missing = to_viewer(stored, self.dataset)
        self.assertEqual(missing, [])
        self.assertEqual(config["group_by"], ["Provincie"])
        self.assertEqual(config["split_by"], ["Betrokkenheidsfase"])
        self.assertEqual(config["filter"][0], ["Betrokkenheidsfase", "in", ["Vaste bezoeker", "Afgehaakt"]])
        self.assertEqual(config["columns"], ["Kinderen", "ratio"])
        self.assertEqual(config["sort"], [["Kinderen", "desc"]])
        self.assertIn('"Bijgewoonde sessies (180 dagen)"', config["expressions"]["ratio"])

    def test_a_column_the_dataset_lost_is_dropped(self):
        stored = {
            "group_by": ["col:gone", "col:province"],
            "filter": [["col:gone", "==", "x"]],
            "aggregates": {"col:gone": "sum"},
            "expressions": {"e": '"col:gone" + 1'},
        }
        with translation.override("en-us"):
            config, missing = to_viewer(stored, self.dataset)
        self.assertEqual(missing, ["gone"])
        self.assertEqual(config["group_by"], ["Province"])
        self.assertEqual((config["filter"], config["aggregates"], config["expressions"]), ([], {}, {}))

    def test_parse_refuses_what_isnt_a_settings_object(self):
        self.assertEqual(parse('{"plugin": "Datagrid"}'), {"plugin": "Datagrid"})
        for raw in ("[]", "not json", "{" + '"a": "' + "x" * 70000 + '"}'):
            with self.assertRaises(ConfigError):
                parse(raw)


@override_settings(REPORT_MIN_GROUP=1)
class ReportPageTests(TestCase):
    def setUp(self):
        cache.clear()
        self.admin = User.objects.create(username="admin", email="admin@example.com")
        OrganisationRole.objects.create(account=self.admin, role=OrganisationRole.ADMIN)
        self.admin = User.objects.get(pk=self.admin.pk)
        dojo = make_dojo("Ghent")
        ninja = Ninja.objects.create(name="Emma", date_of_birth=date(timezone.localdate().year - 10, 1, 1))
        NinjaEngagement.objects.create(
            ninja=ninja, main_dojo=dojo, stage=NinjaEngagement.REGULAR, computed_on=timezone.localdate()
        )
        self.config = json.dumps({"plugin": "Datagrid", "group_by": ["Main dojo"], "columns": ["Children"]})

    def _report(self):
        return Report.objects.create(
            name="Per dojo", dataset="engagement", config={"group_by": ["col:main_dojo"]}, created_by=self.admin
        )

    def test_the_area_is_for_whoever_holds_it(self):
        url = reverse("manage_report_list")
        self.assertEqual(self.client.get(url).status_code, 302)  # logged out: the login page
        board = User.objects.create(username="board")
        OrganisationRole.objects.create(account=board, role=OrganisationRole.BOARD)
        for user in (User.objects.create(username="parent"), board):
            self.client.force_login(user)
            self.assertEqual(self.client.get(url).status_code, 404)
            self.assertEqual(self.client.get(reverse("manage_report_data", args=["engagement"])).status_code, 404)
        self.client.force_login(self.admin)
        response = self.client.get(url)
        self.assertContains(response, "Children and how they come")
        self.assertContains(response, reverse("manage_report_create", args=["engagement"]))

    def test_view_only_can_open_but_not_change(self):
        from django.contrib.auth.models import Permission

        viewer = User.objects.create(username="viewer")
        viewer.user_permissions.add(Permission.objects.get(codename="view_report"))
        report = self._report()
        self.client.force_login(viewer)
        response = self.client.get(reverse("manage_report_detail", args=[report.id]))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'id="report-form"')
        post = {"name": "x", "status": "draft", "config": self.config}
        self.assertEqual(self.client.post(reverse("manage_report_detail", args=[report.id]), post).status_code, 403)
        self.assertEqual(self.client.post(reverse("manage_report_create", args=["engagement"]), post).status_code, 403)
        self.assertEqual(self.client.post(reverse("manage_report_delete", args=[report.id])).status_code, 403)

    def test_data_and_csv(self):
        self.client.force_login(self.admin)
        data = self.client.get(reverse("manage_report_data", args=["engagement"])).json()
        self.assertEqual(data["hidden"], 0)
        self.assertEqual(data["rows"][0]["Main dojo"], "Ghent")
        self.assertEqual(data["rows"][0]["Children"], 1)
        response = self.client.get(reverse("manage_report_csv", args=["engagement"]))
        self.assertEqual(response["Content-Type"], "text/csv; charset=utf-8")
        self.assertIn("Engagement stage,Main dojo", response.content.decode("utf-8-sig"))
        self.assertEqual(self.client.get(reverse("manage_report_data", args=["nope"])).status_code, 404)

    def test_create_save_as_new_and_delete(self):
        self.client.force_login(self.admin)
        response = self.client.post(
            reverse("manage_report_create", args=["engagement"]),
            {"name": "Per dojo", "status": "draft", "description": "Children per dojo.", "config": self.config},
        )
        report = Report.objects.get()
        self.assertRedirects(response, reverse("manage_report_detail", args=[report.id]))
        self.assertEqual(report.config["group_by"], ["col:main_dojo"])
        self.assertEqual((report.created_by, report.updated_by), (self.admin, self.admin))

        url = reverse("manage_report_detail", args=[report.id])
        page = self.client.get(url)
        self.assertContains(page, 'id="report-viewer"')
        self.assertEqual(page.context["setup"]["config"]["group_by"], ["Main dojo"])

        self.client.post(url, {"name": "Copy", "status": "draft", "config": self.config, "save_as_new": "1"})
        self.assertEqual(sorted(Report.objects.values_list("name", flat=True)), ["Copy", "Per dojo"])
        self.client.post(url, {"name": "Renamed", "status": "draft", "config": self.config})
        self.assertEqual(Report.objects.get(pk=report.id).name, "Renamed")

        self.assertRedirects(
            self.client.post(reverse("manage_report_delete", args=[report.id])), reverse("manage_report_list")
        )
        self.assertFalse(Report.objects.filter(pk=report.id).exists())

    def test_settings_that_cant_be_read_are_refused(self):
        self.client.force_login(self.admin)
        response = self.client.post(
            reverse("manage_report_create", args=["engagement"]), {"name": "x", "status": "draft", "config": "[1"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Report.objects.exists())

    def test_only_report_pages_allow_webassembly(self):
        self.client.force_login(self.admin)
        report = self._report()
        for url in (
            reverse("manage_report_create", args=["engagement"]),
            reverse("manage_report_detail", args=[report.id]),
        ):
            policy = self.client.get(url)["Content-Security-Policy"]
            self.assertIn("'wasm-unsafe-eval'", policy)
            self.assertIn("worker-src 'self' blob:", policy)
            self.assertIn("blob:", policy.split("script-src")[1].split(";")[0])
        for url in (reverse("manage_report_list"), reverse("home")):
            policy = self.client.get(url)["Content-Security-Policy"]
            self.assertNotIn("wasm-unsafe-eval", policy)
            self.assertNotIn("blob:", policy.split("script-src")[1].split(";")[0])


class VendoredPerspectiveTests(SimpleTestCase):
    """report.js imports the vendored Perspective files by relative path:
    each must exist (reports/static/reports/vendor/perspective-*/README.md)."""

    def test_every_import_exists(self):
        import re
        from pathlib import Path

        static = Path(__file__).parent / "static" / "reports"
        script = (static / "report.js").read_text()
        paths = re.findall(r'(?:from|import\(?)\s*"(\./vendor/[^"]+)"', script)
        self.assertGreaterEqual(len(paths), 4)
        for path in paths:
            with self.subTest(path=path):
                self.assertTrue((static / path).is_file())
        # What the bundles load by themselves, next to their own files.
        for name in (
            "client/dist/wasm/perspective-js.wasm",
            "server/dist/wasm/perspective-server.wasm",
            "server/dist/wasm/perspective-server.memory64.wasm",
            "viewer/dist/wasm/perspective-viewer.wasm",
        ):
            self.assertTrue((static / "vendor/perspective-5.5.1" / name).is_file(), name)


class DojoScopeTests(TestCase):
    """A dataset filtered to one dojo (DATA_MODEL_REPORTS.md §30): only that
    dojo's rows, no dojo column, and never merged."""

    def setUp(self):
        self.ghent, self.bruges = make_dojo("Ghent"), make_dojo("Bruges")
        year = timezone.localdate().year
        for i, dojo in enumerate([self.ghent, self.ghent, self.bruges]):
            ninja = Ninja.objects.create(name=f"Kid {i}", date_of_birth=date(year - 10, 1, 1), gender="girl")
            NinjaEngagement.objects.create(
                ninja=ninja, main_dojo=dojo, stage=NinjaEngagement.REGULAR, computed_on=timezone.localdate()
            )

    def test_one_dojos_rows_unmerged_without_the_dojo_column(self):
        dataset = EngagementDataset()
        table = dataset.table(dojo=self.ghent)
        self.assertEqual(table.hidden, 0)
        [row] = table.rows
        self.assertNotIn("main_dojo", row)
        self.assertEqual(row["ninjas"], 2)  # below the threshold, still shown
        with translation.override("en-us"):
            [labelled] = dataset.labelled(table, self.ghent)
        self.assertNotIn("Main dojo", labelled)
        self.assertEqual(labelled["Children"], 2)

    def test_settings_on_the_dojo_column_are_dropped_silently(self):
        stored = {"group_by": ["col:main_dojo", "col:stage"], "filter": [["col:main_dojo", "==", "Ghent"]]}
        with translation.override("en-us"):
            config, missing = to_viewer(stored, EngagementDataset(), self.ghent)
        self.assertEqual((config["group_by"], config["filter"], missing), (["Engagement stage"], [], []))


class StandardReportTests(TestCase):
    def test_install_creates_shares_and_respects_edits(self):
        from .standard_reports import STANDARD_REPORTS, StandardReport, install

        self.assertEqual(install(), {"created": len(STANDARD_REPORTS), "updated": 0})
        self.assertEqual(install(), {"created": 0, "updated": 0})
        report = Report.objects.get(standard_key="children_per_stage")
        self.assertTrue(report.is_shared)
        with translation.override("nl-be"):
            self.assertEqual(report.label(), "Kinderen per betrokkenheidsfase")

        # A newer version in the code updates the unedited one...
        old = STANDARD_REPORTS["children_per_stage"]
        newer = StandardReport(old.key, old.name, old.description, old.dataset, {**old.config, "plugin": "X Bar"})
        edited = Report.objects.get(standard_key="regular_and_lapsed")
        edited.name = "Ours now"
        edited.save()
        old_lapsed = STANDARD_REPORTS["regular_and_lapsed"]
        newer_lapsed = StandardReport(
            old_lapsed.key, old_lapsed.name, old_lapsed.description, old_lapsed.dataset, {"plugin": "Y Line"}
        )
        patched = {**STANDARD_REPORTS, old.key: newer, old_lapsed.key: newer_lapsed}
        from unittest import mock

        with mock.patch.dict("reports.standard_reports.STANDARD_REPORTS", patched):
            self.assertEqual(install(), {"created": 0, "updated": 1})
        self.assertEqual(Report.objects.get(standard_key="children_per_stage").config["plugin"], "X Bar")
        # ...never one an admin changed: it's theirs, shown as they wrote it.
        edited.refresh_from_db()
        self.assertEqual((edited.name, edited.config.get("plugin")), ("Ours now", "Datagrid"))
        self.assertEqual(edited.label(), "Ours now")


class DojoReportPageTests(TestCase):
    def setUp(self):
        from dojos.testing import add_member, make_champion, make_mentor

        cache.clear()
        self.champion = make_champion(username="champ", email="champ@example.com")
        self.dojo = make_dojo("Ghent", champion=self.champion)
        self.mentor = make_mentor(username="mentor", email="mentor@example.com")
        add_member(self.dojo, self.mentor)
        self.other_champion = make_champion(username="other", email="other@example.com")
        self.other = make_dojo("Bruges", champion=self.other_champion)
        year = timezone.localdate().year
        for i, dojo in enumerate([self.dojo, self.other, self.other]):
            ninja = Ninja.objects.create(name=f"Kid {i}", date_of_birth=date(year - 10, 1, 1))
            NinjaEngagement.objects.create(
                ninja=ninja, main_dojo=dojo, stage=NinjaEngagement.REGULAR, computed_on=timezone.localdate()
            )
        self.shared = Report.objects.create(
            name="Shared", dataset="engagement", status=Report.PUBLISHED, shared_with_dojos=True
        )
        self.draft = Report.objects.create(name="Draft one", dataset="engagement", shared_with_dojos=True)
        self.organisation_only = Report.objects.create(name="Ours", dataset="engagement", status=Report.PUBLISHED)

    def _url(self, name, **kwargs):
        return reverse(name, kwargs={"dojo_id": self.dojo.id, **kwargs})

    def test_the_champion_sees_published_shared_reports_only(self):
        self.client.force_login(self.champion)
        response = self.client.get(self._url("dojo_report_list"))
        self.assertContains(response, "Shared")
        self.assertNotContains(response, "Draft one")
        self.assertNotContains(response, "Ours")
        self.assertContains(
            self.client.get(reverse("dojo_dashboard", args=[self.dojo.id])), self._url("dojo_report_list")
        )
        detail = self.client.get(self._url("dojo_report_detail", report_id=self.shared.id))
        self.assertContains(detail, 'id="report-viewer"')
        self.assertNotContains(detail, 'id="report-form"')
        self.assertIn("'wasm-unsafe-eval'", detail["Content-Security-Policy"])
        for report in (self.draft, self.organisation_only):
            self.assertEqual(self.client.get(self._url("dojo_report_detail", report_id=report.id)).status_code, 404)

    def test_figures_are_the_dojos_own(self):
        self.client.force_login(self.champion)
        data = self.client.get(self._url("dojo_report_data", dataset_key="engagement")).json()
        self.assertEqual(sum(row["Children"] for row in data["rows"]), 1)
        self.assertNotIn("Main dojo", data["rows"][0])
        csv_text = self.client.get(self._url("dojo_report_csv", dataset_key="engagement")).content.decode("utf-8-sig")
        self.assertNotIn("Main dojo", csv_text)
        # Another dojo's figures: not this champion's dojo.
        other = reverse("dojo_report_data", kwargs={"dojo_id": self.other.id, "dataset_key": "engagement"})
        self.assertEqual(self.client.get(other).status_code, 404)

    def test_mentors_and_strangers_get_nothing(self):
        self.client.force_login(self.mentor)
        self.assertEqual(self.client.get(self._url("dojo_report_list")).status_code, 403)
        self.assertEqual(self.client.get(self._url("dojo_report_data", dataset_key="engagement")).status_code, 403)
        self.assertNotContains(
            self.client.get(reverse("dojo_dashboard", args=[self.dojo.id])), self._url("dojo_report_list")
        )
        self.client.force_login(self.other_champion)
        self.assertEqual(self.client.get(self._url("dojo_report_list")).status_code, 404)

    def test_the_organisation_publishes_and_shares(self):
        admin = User.objects.create(username="admin", email="admin@example.com")
        OrganisationRole.objects.create(account=admin, role=OrganisationRole.ADMIN)
        self.client.force_login(User.objects.get(pk=admin.pk))
        self.client.post(
            reverse("manage_report_create", args=["engagement"]),
            {
                "name": "New one",
                "status": Report.PUBLISHED,
                "shared_with_dojos": "on",
                "position": "5",
                "config": "{}",
            },
        )
        report = Report.objects.get(name="New one")
        self.assertTrue(report.is_shared)
        self.assertEqual(report.position, 5)
        self.client.force_login(self.champion)
        self.assertContains(self.client.get(self._url("dojo_report_list")), "New one")
