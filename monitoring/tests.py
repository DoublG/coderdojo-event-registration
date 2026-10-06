import json
from io import StringIO
from unittest import mock

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings
from django.urls import reverse
from django_redis import get_redis_connection

from monitoring import capacity, celery_signals, collect, recorder
from monitoring.models import CapacitySample
from monitoring.tasks import take_sample


def clear_counters():
    recorder._reporting_pid = None
    get_redis_connection("default").delete(
        recorder.REQUESTS_KEY,
        recorder.TASKS_KEY,
        recorder.CACHE_KEY,
        *get_redis_connection("default").keys(f"{recorder.PROCESS_KEY_PREFIX}*"),
    )


class RecorderTests(TestCase):
    def setUp(self):
        clear_counters()

    def test_a_request_is_counted_per_view_with_its_time_and_bucket(self):
        self.client.get(reverse("home"))
        counts = recorder.requests()["home"]
        self.assertEqual(counts["count"], 1)
        self.assertGreaterEqual(counts["ms"], 0)
        self.assertEqual(counts.get("5xx", 0), 0)
        # Each bucket counts the requests that took at most its bound.
        buckets = [counts.get(f"le_{bound}", 0) for bound in recorder.DURATION_BUCKETS_MS]
        self.assertEqual(buckets, sorted(buckets))

    def test_a_request_counts_its_database_queries_and_data_cache_reads(self):
        from django.core.cache import cache

        cache.clear()
        self.client.get(reverse("home"))  # builds the home page's caches
        self.client.get(reverse("home"))  # reads them
        self.assertGreater(recorder.requests()["home"]["queries"], 0)
        sponsors = recorder.cache_reads()["content:sponsors"]
        self.assertEqual((sponsors["misses"], sponsors["hits"]), (1, 1))

    def test_a_cache_read_outside_a_request_is_not_counted(self):
        recorder.note_cache("anything", hit=True)
        self.assertNotIn("anything", recorder.cache_reads())

    def test_a_server_error_is_counted(self):
        recorder.record_request("some_view", 12, 503)
        self.assertEqual(recorder.requests()["some_view"]["5xx"], 1)

    def test_a_request_starts_the_process_reporting_its_memory(self):
        self.client.get(reverse("home"))
        self.client.get(reverse("home"))
        processes = recorder.processes()
        self.assertEqual(len(processes), 1)
        self.assertEqual(processes[0]["role"], "web")
        self.assertGreater(processes[0]["rss"], 0)
        self.assertGreaterEqual(processes[0]["max_rss"], processes[0]["rss"] // 2)
        # Once per process: later requests don't start another reporter.
        with mock.patch("monitoring.recorder.threading.Thread") as thread:
            self.client.get(reverse("home"))
        thread.assert_not_called()

    def test_a_report_expires_and_a_clean_exit_removes_it(self):
        recorder.report_process("web")
        key = recorder._process_key("web")
        self.assertLessEqual(get_redis_connection("default").ttl(key), recorder.PROCESS_TTL)
        recorder._forget("web")
        self.assertEqual(recorder.processes(), [])

    def test_a_redis_that_is_down_never_fails_the_request(self):
        with mock.patch("monitoring.recorder.get_redis_connection", side_effect=ConnectionError("down")):
            response = self.client.get(reverse("home"))
        self.assertEqual(response.status_code, 200)

    @override_settings(METRICS_SLOW_REQUEST_MS=0)
    def test_a_slow_request_is_logged(self):
        with self.assertLogs("monitoring.middleware", "WARNING") as logs:
            self.client.get(reverse("home"))
        self.assertIn("(home)", logs.output[0])

    @override_settings(METRICS_ENABLED=False)
    def test_switched_off_it_records_nothing(self):
        self.client.get(reverse("home"))
        self.assertEqual(recorder.requests(), {})

    def test_a_task_is_timed_through_celerys_signals(self):
        task = mock.Mock()
        task.name = "mailing.tasks.send_pending_emails"
        celery_signals._task_started(task_id="a")
        celery_signals._task_finished(task_id="a", task=task, state="SUCCESS")
        celery_signals._task_started(task_id="b")
        celery_signals._task_finished(task_id="b", task=task, state="FAILURE")
        stats = recorder.tasks()["mailing.tasks.send_pending_emails"]
        self.assertEqual(stats["count"], 2)
        self.assertEqual(stats["failures"], 1)
        self.assertIn("max_seconds", stats)
        self.assertEqual(recorder.processes()[0]["role"], "celery")


class MetricsViewTests(TestCase):
    def setUp(self):
        clear_counters()

    def test_without_a_configured_token_it_does_not_exist(self):
        with override_settings(METRICS_TOKEN=""):
            self.assertEqual(self.client.get(reverse("metrics")).status_code, 404)

    @override_settings(METRICS_TOKEN="secret")
    def test_a_wrong_or_missing_token_is_refused(self):
        self.assertEqual(self.client.get(reverse("metrics")).status_code, 401)
        response = self.client.get(reverse("metrics"), HTTP_AUTHORIZATION="Bearer wrong")
        self.assertEqual(response.status_code, 401)

    @override_settings(METRICS_TOKEN="secret")
    def test_with_the_token_it_shows_every_component(self):
        self.client.get(reverse("home"))
        response = self.client.get(reverse("metrics"), HTTP_AUTHORIZATION="Bearer secret")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response["Content-Type"].startswith("text/plain; version=0.0.4"))
        self.assertIn("no-cache", response["Cache-Control"])
        text = response.content.decode()
        for metric in (
            'coderdojo_db_table_bytes{table="accounts_user"}',
            "coderdojo_mysql_threads_connected",
            "coderdojo_redis_used_memory_bytes",
            'coderdojo_celery_queue_length{queue="periodic"}',
            "coderdojo_mail_pending 0",
            "coderdojo_websocket_connections",
            'coderdojo_http_requests_total{view="home"} 1',
            'coderdojo_http_request_duration_ms_bucket{view="home",le="+Inf"} 1',
            'coderdojo_http_db_queries_total{view="home"}',
            'coderdojo_cache_hits_total{cache="content:sponsors"}',
            'coderdojo_cache_misses_total{cache="content:sponsors"}',
            'coderdojo_process_rss_bytes{role="web"',
        ):
            self.assertIn(metric, text)
        self.assertIn('coderdojo_metrics_section_up{section="redis"} 1', text)

    @override_settings(METRICS_TOKEN="secret")
    def test_a_component_that_is_down_is_marked_and_the_rest_still_shows(self):
        with (
            mock.patch("monitoring.collect.get_redis_connection", side_effect=ConnectionError("down")),
            self.assertLogs("monitoring.views", "ERROR"),
        ):
            response = self.client.get(reverse("metrics"), HTTP_AUTHORIZATION="Bearer secret")
        text = response.content.decode()
        self.assertIn('coderdojo_metrics_section_up{section="redis"} 0', text)
        self.assertIn('coderdojo_metrics_section_up{section="database"} 1', text)

    def test_silks_tables_are_left_out(self):
        cursor = mock.MagicMock()
        cursor.__enter__.return_value.fetchall.return_value = [
            ("silk_request", 5, 100, 10),
            ("accounts_user", 2, 16384, 0),
        ]
        with mock.patch("monitoring.collect.connection.cursor", return_value=cursor):
            self.assertEqual(
                collect.database_tables(), {"accounts_user": {"rows": 2, "data_bytes": 16384, "index_bytes": 0}}
            )


class CapacitySampleTests(TestCase):
    def test_the_daily_sample_holds_every_part(self):
        sample = take_sample()
        self.assertEqual(
            set(sample.data),
            set(("tables", "mysql", "redis", "queues", "mail", "websockets", "processes", "requests", "tasks")),
        )
        self.assertIn("accounts_user", sample.data["tables"])
        self.assertGreater(sample.database_bytes, 0)
        self.assertEqual(str(sample), f"Capacity sample {sample.taken_on}")

    def test_a_second_sample_the_same_day_replaces_the_first(self):
        take_sample()
        take_sample()
        self.assertEqual(CapacitySample.objects.count(), 1)

    def test_a_part_that_fails_is_left_out_not_the_sample(self):
        with (
            mock.patch.dict("monitoring.tasks.PARTS", {"redis": mock.Mock(side_effect=ConnectionError("down"))}),
            self.assertLogs("monitoring.tasks", "ERROR"),
        ):
            sample = take_sample()
        self.assertNotIn("redis", sample.data)
        self.assertIn("tables", sample.data)

    def test_it_is_scheduled_daily_on_the_periodic_queue(self):
        entry = settings.CELERY_BEAT_SCHEDULE["capacity-sample"]
        self.assertEqual(entry["task"], "monitoring.tasks.record_capacity_sample")
        self.assertEqual(settings.CELERY_TASK_ROUTES[entry["task"]], {"queue": "periodic"})


class CapacityModelTests(TestCase):
    SIZES = {"tables": {"mailing_emailmessage": 1000, "events_registration": 200}, "mail_content_bytes": 500}

    def test_yearly_tables_add_up_and_level_tables_stay(self):
        scenario = capacity.SCENARIOS["growth"]
        one = capacity.project(scenario, 1, {}, self.SIZES)
        three = capacity.project(scenario, 3, {}, self.SIZES)
        self.assertEqual(one["mailing_emailmessage"], scenario.mail_per_year * 1000)
        self.assertEqual(three["mailing_emailmessage"], 3 * one["mailing_emailmessage"])
        self.assertEqual(three["events_ninjaengagement"], one["events_ninjaengagement"])
        # Unmeasured tables count the default size per row.
        self.assertEqual(one["events_event"], scenario.sessions * capacity.DEFAULT_ROW_BYTES)

    def test_projection_starts_from_what_the_tables_hold_now(self):
        now = {
            "mailing_emailmessage": {"rows": 10, "data_bytes": 5000, "index_bytes": 5000},
            "geo_municipality": {"rows": 1, "data_bytes": 7, "index_bytes": 0},
        }
        result = capacity.project(capacity.SCENARIOS["today"], 1, now, self.SIZES)
        self.assertEqual(result["mailing_emailmessage"], 10000 + capacity.SCENARIOS["today"].mail_per_year * 1000)
        self.assertEqual(result["geo_municipality"], 7)

    def test_clearing_mail_content_after_a_year_shrinks_older_mail(self):
        scenario = capacity.SCENARIOS["today"]
        kept = capacity.project(scenario, 3, {}, self.SIZES)["mailing_emailmessage"]
        cleared = capacity.project(scenario, 3, {}, self.SIZES, clear_mail_content=True)["mailing_emailmessage"]
        self.assertEqual(kept - cleared, 2 * scenario.mail_per_year * 500)

    def test_every_growing_table_exists(self):
        tables = collect.database_tables()
        self.assertEqual([table for table in capacity.GROWTH if table not in tables], [])

    def test_the_stored_row_sizes_cover_the_big_tables(self):
        sizes = capacity.load_row_sizes()
        for table in ("mailing_emailmessage", "auditlog_logentry", "events_registration"):
            self.assertGreater(sizes["tables"][table], 0)

    def test_the_report_prints_every_scenario(self):
        out = StringIO()
        call_command("capacity_report", "--years", "1", "2", stdout=out)
        text = out.getvalue()
        self.assertIn("## This database now", text)
        for name in capacity.SCENARIOS:
            self.assertIn(f"## Scenario `{name}`", text)
        self.assertIn("Total, mail content cleared after 12 months", text)

    def test_the_json_gives_every_year_of_every_scenario(self):
        out = StringIO()
        call_command("capacity_report", "--json", "--years", "3", stdout=out)
        result = json.loads(out.getvalue())
        growth = result["scenarios"]["growth"]
        self.assertEqual(growth["years"], [0, 1, 2, 3])
        self.assertEqual(len(growth["bytes"]), 4)
        self.assertLess(growth["bytes"][0], growth["bytes"][3])
        self.assertLess(growth["bytes_mail_cleared"][3], growth["bytes"][3])

    def test_measuring_needs_a_scaled_database(self):
        small = {"accounts_user": {"rows": 3, "data_bytes": 16384, "index_bytes": 0}}
        with (
            mock.patch("monitoring.collect.database_tables", return_value=small),
            mock.patch("monitoring.capacity.ROW_SIZES_FILE") as file,
            self.assertRaisesMessage(CommandError, "run seed_scale first"),
        ):
            call_command("capacity_report", "--measure", stdout=StringIO())
        file.write_text.assert_not_called()


TINY = capacity.Scenario("tiny", dojos=3, families=20, sessions_per_dojo=2, bookings_per_session=4)


class SeedScaleTests(TestCase):
    def test_it_refuses_a_database_that_is_not_a_test_database(self):
        with (
            mock.patch.dict(settings.DATABASES["default"], NAME="coolregistration"),
            self.assertRaisesMessage(CommandError, "only a database whose name starts with test_"),
        ):
            call_command("seed_scale", stdout=StringIO())

    @mock.patch.dict("monitoring.capacity.SCENARIOS", {"tiny": TINY})
    def test_it_fills_a_scenario_with_consistent_data(self):
        from accounts.models import Guardianship, Ninja, User
        from events.models import Event, NinjaEngagement, Registration
        from mailing.models import EmailMessage

        call_command("seed_scale", "--scenario", "tiny", "--skip-analyze", stdout=StringIO())
        self.assertEqual(Event.objects.filter(status=Event.CLOSED).count(), 6)
        self.assertEqual(Event.objects.filter(status=Event.OPEN).count(), 6)
        self.assertTrue(User.objects.filter(username="family0").exists())
        self.assertEqual(Guardianship.objects.values("ninja").distinct().count(), Ninja.objects.count())
        self.assertTrue(Registration.objects.exists())
        # Rounded per kind of mail.
        self.assertAlmostEqual(
            EmailMessage.objects.count(), TINY.mail_per_year, delta=len(capacity.mail_breakdown(TINY))
        )
        self.assertTrue(NinjaEngagement.objects.exists())
        self.assertTrue(self.client.login(username="family0", password="scale-test"))

        with self.assertRaisesMessage(CommandError, "already has dojos"):
            call_command("seed_scale", "--scenario", "tiny", stdout=StringIO())


class GunicornConfigTests(TestCase):
    """gunicorn.conf.py caps the requests each web worker takes at once
    (CAPACITY.md, "Capping requests per web worker")."""

    def load(self, **env):
        import runpy

        from django.conf import settings as django_settings
        from uvicorn.workers import UvicornWorker

        original = UvicornWorker.CONFIG_KWARGS
        self.addCleanup(setattr, UvicornWorker, "CONFIG_KWARGS", original)
        with mock.patch.dict("os.environ", env):
            runpy.run_path(str(django_settings.BASE_DIR / "gunicorn.conf.py"))
        return UvicornWorker.CONFIG_KWARGS

    def test_each_worker_takes_at_most_25_at_once(self):
        with mock.patch.dict("os.environ"):
            import os

            os.environ.pop("UVICORN_LIMIT_CONCURRENCY", None)
            config = self.load()
        self.assertEqual(config["limit_concurrency"], 25)
        # uvicorn's own choices stay.
        self.assertEqual(config["loop"], "auto")

    def test_the_environment_can_change_it(self):
        self.assertEqual(self.load(UVICORN_LIMIT_CONCURRENCY="40")["limit_concurrency"], 40)

    def test_reading_it_again_on_a_reload_changes_nothing(self):
        first = dict(self.load())
        self.assertEqual(self.load(), first)


class CeleryForkMemoryTests(TestCase):
    """website.celery freezes the parent's objects before a worker forks, so
    the children keep sharing its memory (DATA_MODEL.md §11)."""

    def test_the_parent_freezes_its_objects_before_each_fork(self):
        import gc

        from celery.signals import worker_before_create_process

        from website.celery import freeze_before_fork

        self.assertIn(freeze_before_fork, [ref() for _, ref in worker_before_create_process.receivers])
        self.addCleanup(gc.unfreeze)
        with mock.patch("gc.collect") as collect:
            worker_before_create_process.send(sender=None)
        collect.assert_called_once()
        self.assertGreater(gc.get_freeze_count(), 0)
