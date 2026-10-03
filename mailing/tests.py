import re
import smtplib
from datetime import timedelta
from io import StringIO
from unittest.mock import patch

from django.contrib.gis.geos import Point
from django.core import mail as django_mail
from django.core.management import call_command
from django.db import transaction
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.consent import consent_fields
from accounts.models import Guardianship, Ninja, User
from campaigns.models import Campaign
from dojos.models import Dojo
from dojos.testing import make_dojo
from events.models import Event, Registration
from geo.models import Municipality
from mailing.testing import FakeConnection, complaint_report, dsn_report, make_family

from .categories import PRIVACY_WORDING_VERSION, MailCategory
from .models import (
    BounceRecord,
    ConsentEvent,
    EmailMessage,
    EmailSuppression,
    EmailTemplate,
    MailPreference,
    ProcessedImapMessage,
)
from .preferences import is_subscribed, preferences_for, set_preference, subscribed_q
from .rendering import TemplateMissing, render
from .services import send, unsubscribe_token
from .tasks import (
    SendBatchTask,
    TransientSendError,
    _claim_pending,
    requeue_stuck_emails,
    send_email_batch,
    send_pending_emails,
)


class RenderingTests(TestCase):
    def setUp(self):
        EmailTemplate.objects.create(
            key="hello", language="en-us", category="service", subject="Hi {{ name }}", body="Hello {{ name }} & <you>"
        )
        EmailTemplate.objects.create(
            key="hello", language="nl-be", category="service", subject="Dag {{ name }}", body="Hallo {{ name }}"
        )

    def test_renders_in_the_requested_language(self):
        self.assertEqual(render("hello", "nl-be", {"name": "An"}), ("Dag An", "Hallo An\n"))

    def test_falls_back_to_english(self):
        self.assertEqual(render("hello", "fr-be", {"name": "An"})[0], "Hi An")

    def test_plain_text_is_not_html_escaped(self):
        self.assertEqual(render("hello", "en-us", {"name": "A&B"})[1], "Hello A&B & <you>\n")

    def test_missing_template(self):
        with self.assertRaises(TemplateMissing):
            render("nope", "en-us", {})


# --- phase 3: preferences, the send() gateway, the queue ---------------------

Status = EmailMessage.Status


def _templates():
    for language, greeting in [("en-us", "Hello"), ("nl-be", "Hallo")]:
        EmailTemplate.objects.create(
            key="note",
            language=language,
            category=MailCategory.REMINDER,
            subject=f"{greeting} {{{{ recipient_name }}}}",
            body=f"{greeting}! {{{{ extra }}}} {{{{ unsubscribe_url }}}}",
        )
    EmailTemplate.objects.create(
        key="account",
        language="en-us",
        category=MailCategory.SERVICE,
        subject="Your account",
        body="Account mail. {{ unsubscribe_url }}",
    )


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
        self.assertEqual(
            set(preferences_for(self.teen)),
            {MailCategory.SERVICE, MailCategory.REGISTRATION, MailCategory.REMINDER, MailCategory.DOJO_NEWS},
        )
        self.assertFalse(is_subscribed(self.teen, MailCategory.NEWSLETTER))
        self.assertFalse(set_preference(self.teen, MailCategory.NEWSLETTER, True, ConsentEvent.PREFERENCES))
        self.assertFalse(is_subscribed(self.teen, MailCategory.NEWSLETTER))

    def test_changes_are_logged_once(self):
        self.assertTrue(set_preference(self.parent, MailCategory.NEWSLETTER, True, ConsentEvent.SIGNUP))
        self.assertFalse(set_preference(self.parent, MailCategory.NEWSLETTER, True, ConsentEvent.PREFERENCES))
        self.assertTrue(set_preference(self.parent, MailCategory.NEWSLETTER, False, ConsentEvent.UNSUBSCRIBE_LINK))
        log = list(ConsentEvent.objects.order_by("id").values_list("subscribed", "source", "wording_version"))
        version = PRIVACY_WORDING_VERSION
        self.assertEqual(log, [(True, "signup", version), (False, "unsubscribe_link", version)])

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
                in_db = set(
                    User.objects.filter(pk__in=[self.parent.pk, other.pk])
                    .filter(subscribed_q(category))
                    .values_list("username", flat=True)
                )
                in_python = {u.username for u in (self.parent, other) if is_subscribed(u, category)}
                self.assertEqual(in_db, in_python)


class SendGatewayTests(TestCase):
    def setUp(self):
        _templates()
        self.user = User.objects.create(
            username="ellen", first_name="Ellen", email="ellen@example.com", preferred_language="nl-be"
        )

    def test_queues_a_rendered_mail_in_the_recipients_language(self):
        row = send(self.user, MailCategory.REMINDER, "note", {"extra": "Tot zaterdag"})
        self.assertEqual(
            (row.status, row.recipient, row.language, row.subject),
            (Status.PENDING, "ellen@example.com", "nl-be", "Hallo Ellen"),
        )
        self.assertIn("Tot zaterdag", row.body)
        self.assertIn("/mail/unsubscribe/", row.body)
        self.assertEqual(row.priority, 5)
        self.assertEqual(len(django_mail.outbox), 0)  # queued, not sent

    def test_mail_that_cant_be_switched_off_has_no_unsubscribe_link(self):
        row = send(self.user, MailCategory.SERVICE, "account")
        self.assertNotIn("/mail/unsubscribe/", row.body)
        self.assertEqual(row.priority, 0)

    def test_service_mail_can_go_to_another_address_and_is_still_checked_against_blocks(self):
        row = send(self.user, MailCategory.SERVICE, "account", address=" ellen.new@example.com ")
        self.assertEqual((row.status, row.recipient, row.user), (Status.PENDING, "ellen.new@example.com", self.user))
        EmailSuppression.objects.create(email="blocked@example.com", reason=EmailSuppression.HARD_BOUNCE)
        row = send(self.user, MailCategory.SERVICE, "account", address="blocked@example.com")
        self.assertEqual(row.status, Status.SUPPRESSED)
        with self.assertRaises(ValueError):
            send(self.user, MailCategory.REMINDER, "note", address="ellen.new@example.com")

    def test_suppressed_with_a_reason(self):
        cases = {
            "unsubscribed": lambda: set_preference(self.user, MailCategory.REMINDER, False, ConsentEvent.PREFERENCES),
            "blocked": lambda: EmailSuppression.objects.create(
                email="Ellen@Example.com ", reason=EmailSuppression.HARD_BOUNCE
            ),
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
        EmailMessage.objects.filter(pk__in=[r.pk for r in rows]).update(
            status=Status.SENDING, claimed_at=timezone.now()
        )

    def test_batch_sends_with_message_id_and_unsubscribe_headers(self):
        reminder, account = self._queue(self.users[0]), self._queue(self.users[1], MailCategory.SERVICE)
        self._claimed(reminder, account)
        connection = FakeConnection()
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
        with patch("mailing.tasks.mail.get_connection", return_value=FakeConnection({"u0@example.com": refused})):
            send_email_batch([r.pk for r in rows])
        statuses = dict(EmailMessage.objects.values_list("recipient", "status"))
        self.assertEqual(statuses, {"u0@example.com": Status.FAILED, "u1@example.com": Status.SENT})

    def test_a_server_problem_is_retried_and_never_resends(self):
        rows = [self._queue(u) for u in self.users[:2]]
        self._claimed(*rows)
        down = smtplib.SMTPServerDisconnected("gone")
        with patch("mailing.tasks.mail.get_connection", return_value=FakeConnection({"u1@example.com": down})):
            with self.assertRaises(TransientSendError):
                send_email_batch([r.pk for r in rows])
        self.assertEqual(
            dict(EmailMessage.objects.values_list("recipient", "status")),
            {"u0@example.com": Status.SENT, "u1@example.com": Status.SENDING},
        )

        connection = FakeConnection()
        with patch("mailing.tasks.mail.get_connection", return_value=connection):
            send_email_batch([r.pk for r in rows])
        self.assertEqual([m.to[0] for m in connection.sent], ["u1@example.com"])

    def test_after_the_last_retry_the_rest_of_the_batch_fails(self):
        rows = [self._queue(u) for u in self.users[:2]]
        self._claimed(*rows)
        EmailMessage.objects.filter(pk=rows[0].pk).update(status=Status.SENT)
        SendBatchTask().on_failure(RuntimeError("smtp down"), "task-id", ([r.pk for r in rows],), {}, None)
        self.assertEqual(
            dict(EmailMessage.objects.values_list("recipient", "status")),
            {"u0@example.com": Status.SENT, "u1@example.com": Status.FAILED},
        )

    @override_settings(MAILING_CLAIM_TIMEOUT_MINUTES=60)
    def test_requeue_stuck_rows(self):
        stuck, fresh = self._queue(self.users[0]), self._queue(self.users[1])
        EmailMessage.objects.filter(pk=stuck.pk).update(
            status=Status.SENDING, claimed_at=timezone.now() - timedelta(hours=2)
        )
        EmailMessage.objects.filter(pk=fresh.pk).update(status=Status.SENDING, claimed_at=timezone.now())
        self.assertEqual(requeue_stuck_emails(), 1)
        self.assertEqual(
            dict(EmailMessage.objects.values_list("pk", "status")),
            {stuck.pk: Status.PENDING, fresh.pk: Status.SENDING},
        )


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

    def test_saving_changes_preferences_and_language(self):
        self.client.force_login(self.parent)
        response = self.client.post(
            reverse("mail_preferences"),
            {
                "category_newsletter": "on",
                "category_dojo_news": "on",
                "category_volunteer": "on",
                "preferred_language": "fr-be",
                # The postcode moved to the account page's details (accounts.views.edit_account).
                "postal_code": "9000",
            },
        )
        self.assertRedirects(response, reverse("mail_preferences"))
        self.assertTrue(is_subscribed(self.parent, MailCategory.NEWSLETTER))
        self.assertFalse(is_subscribed(self.parent, MailCategory.REMINDER))
        self.parent.refresh_from_db()
        self.assertEqual((self.parent.preferred_language, self.parent.postal_code), ("fr-be", ""))
        self.assertNotContains(self.client.get(reverse("mail_preferences")), 'name="postal_code"')
        self.assertEqual(
            set(ConsentEvent.objects.values_list("category", "source")),
            {("newsletter", "preferences"), ("reminder", "preferences")},
        )

    def test_a_switch_per_child_gives_or_withdraws_the_consent(self):
        from accounts.consent import CHILD_DATA_WORDING_VERSION

        lotte = Ninja.objects.create(name="Lotte")
        mats = Ninja.objects.create(name="Mats")
        Guardianship.objects.create(guardian=self.parent, ninja=lotte, **consent_fields())
        Guardianship.objects.create(guardian=self.parent, ninja=mats)
        self.client.force_login(self.parent)
        response = self.client.get(reverse("mail_preferences"))
        self.assertContains(response, "Use my children's details")
        self.assertTrue(response.context["form"][f"child_{lotte.id}"].initial)
        self.assertFalse(response.context["form"][f"child_{mats.id}"].initial)

        self.client.post(reverse("mail_preferences"), {"preferred_language": "nl-be", f"child_{mats.id}": "on"})
        lotte_link = Guardianship.objects.get(ninja=lotte)
        mats_link = Guardianship.objects.get(ninja=mats)
        self.assertEqual((lotte_link.consent_given_at, lotte_link.consent_wording_version), (None, ""))
        self.assertIsNotNone(mats_link.consent_given_at)
        self.assertEqual(mats_link.consent_wording_version, CHILD_DATA_WORDING_VERSION)

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
        self.assertEqual(
            {c for c, on in preferences_for(self.user).items() if on},
            {MailCategory.SERVICE, MailCategory.REGISTRATION},
        )

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
            status=Status.SENT, message_id="<123.456.789@coolregistration.localhost>"
        )
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
        self.assertEqual(
            (record.kind, record.status_code, record.message_id), (BounceRecord.HARD, "5.1.1", self.row.pk)
        )
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
        self.assertEqual(
            {c for c, on in preferences_for(self.user).items() if on},
            {MailCategory.SERVICE, MailCategory.REGISTRATION},
        )
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

    @override_settings(
        MAILING_BOUNCE_ADDRESS="bounces+{id}@example.org", DEFAULT_FROM_EMAIL="CoderDojo <noreply@example.org>"
    )
    def test_mail_goes_out_with_the_bounce_address_as_envelope_sender(self):
        from .tasks import _build

        message, _message_id = _build(self.row)
        self.assertEqual(message.from_email, f"bounces+{self.row.pk}@example.org")
        self.assertEqual(message.message()["From"], "CoderDojo <noreply@example.org>")

    # SSL off, like the devcontainer's Mailpit: the patch below replaces plain POP3.
    @override_settings(
        MAILING_BOUNCE_IMAP_HOST="mailpit", MAILING_BOUNCE_PROTOCOL="pop3", MAILING_BOUNCE_IMAP_SSL=False
    )
    def test_an_unreachable_mailbox_is_a_warning_not_a_crash(self):
        from .tasks import process_bounces

        with patch("mailing.bounce.poplib.POP3", side_effect=ConnectionRefusedError(111, "refused")):
            with self.assertLogs("mailing.tasks", level="WARNING"):
                self.assertEqual(process_bounces(), 0)

    @override_settings(MAILING_BOUNCE_IMAP_HOST="")
    def test_off_without_a_mailbox(self):
        from .tasks import process_bounces

        self.assertEqual(process_bounces(), 0)


@override_settings(
    MAILING_BOUNCE_IMAP_HOST="imap.example.org",
    MAILING_BOUNCE_IMAP_MAILBOX="Bounces",
    MAILING_BOUNCE_IMAP_SSL=True,
    MAILING_BOUNCE_PROTOCOL="imap",
)
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
        self.parent = User.objects.create(
            username="parent", first_name="Ellen", email="p@example.com", preferred_language="nl-be"
        )
        self.co_parent = User.objects.create(username="co", email="co@example.com")
        self.teen_login = User.objects.create(username="teen", email="t@example.com", account_type=User.NINJA)
        self.kid = Ninja.objects.create(
            name="Emma", family_name="Peeters", account=self.teen_login, home_dojo=self.dojo
        )
        for guardian in (self.parent, self.co_parent):
            Guardianship.objects.create(guardian=guardian, ninja=self.kid)

    def _event(self, days_ahead=2, status=Event.OPEN, places=10, dojo=None, name="Scratch"):
        start = timezone.now().replace(hour=14, minute=0, second=0, microsecond=0) + timedelta(days=days_ahead)
        return Event.objects.create(
            name=name,
            dojo=dojo or self.dojo,
            status=status,
            places=places,
            start_time=start,
            end_time=start + timedelta(hours=2),
        )

    def _mails(self, **filters):
        return list(
            EmailMessage.objects.filter(**filters).order_by("id").values_list("recipient", "template_key", "status")
        )

    def test_family_is_guardians_and_own_login_with_email(self):
        from .automated import family_of

        User.objects.filter(pk=self.co_parent.pk).update(email="")
        self.assertEqual([u.username for u in family_of(self.kid)], ["parent", "teen"])

    def test_signup_confirms_to_the_whole_family(self):
        event = self._event(days_ahead=10)
        self.client.force_login(self.parent)
        self.client.post(
            reverse("event_signup", kwargs={"event_id": event.id}),
            {"child": [str(self.kid.id)], "child_order": str(self.kid.id)},
        )
        self.assertEqual(
            self._mails(),
            [
                ("p@example.com", "registration_confirmed", Status.PENDING),
                ("co@example.com", "registration_confirmed", Status.PENDING),
                ("t@example.com", "registration_confirmed", Status.PENDING),
            ],
        )
        dutch = EmailMessage.objects.get(recipient="p@example.com")
        self.assertEqual(dutch.subject, "Emma is ingeschreven voor Scratch")

    def test_signup_for_a_full_session_sends_the_waiting_list_notice(self):
        event = self._event(days_ahead=10, places=0)
        self.client.force_login(self.parent)
        self.client.post(
            reverse("event_signup", kwargs={"event_id": event.id}),
            {"child": [str(self.kid.id)], "child_order": str(self.kid.id)},
        )
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

        self.assertEqual(
            {(r, k) for r, k, _s in self._mails()},
            {
                ("p@example.com", "waitlist_promoted"),
                ("co@example.com", "waitlist_promoted"),
                ("t@example.com", "waitlist_promoted"),
            },
        )

    def test_a_missing_template_never_breaks_a_signup(self):
        EmailTemplate.objects.all().delete()
        event = self._event(days_ahead=10)
        self.client.force_login(self.parent)
        with self.assertLogs("mailing.automated", level="ERROR"):
            self.client.post(
                reverse("event_signup", kwargs={"event_id": event.id}),
                {"child": [str(self.kid.id)], "child_order": str(self.kid.id)},
            )
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
        self.assertEqual(
            self._mails(template_key="session_reminder"),
            [
                ("p@example.com", "session_reminder", Status.PENDING),
                ("co@example.com", "session_reminder", Status.PENDING),
                ("t@example.com", "session_reminder", Status.SUPPRESSED),
            ],
        )

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
        self.assertEqual(
            set(ghent.values_list("recipient", flat=True)),
            {"p@example.com", "co@example.com", "t@example.com", "v@example.com"},
        )
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
            if (
                relative in self.ALLOWED
                or "/migrations/" in relative
                or relative.endswith("tests.py")
                or relative.startswith((".", "docs/", "static/", "media/"))
            ):
                continue
            for number, line in enumerate(path.read_text(errors="ignore").splitlines(), 1):
                if self.DIRECT_SEND.search(line) and not line.lstrip().startswith("#"):
                    offenders.append(f"{relative}:{number}: {line.strip()}")
        self.assertEqual(offenders, [], "send mail through mailing.services.send() instead")


# --- phase 8: campaigns from the organisation dashboard ---------------------------


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
        response = self.client.post(
            self._edit("session_reminder", "nl-be"),
            {
                "subject": "Tot {{ start_time|date:'l' }}!",
                "body": "Hallo {{ recipient_name }}",
                "description": "d",
            },
        )
        self.assertRedirects(response, self._edit("session_reminder", "nl-be"))
        self.assertEqual(
            EmailTemplate.objects.get(key="session_reminder", language="nl-be").subject,
            "Tot {{ start_time|date:'l' }}!",
        )

    def test_a_broken_template_is_refused(self):
        response = self.client.post(
            self._edit("session_reminder"), {"subject": "Hi", "body": "{% if %}", "description": ""}
        )
        self.assertContains(response, "doesn&#x27;t work as a template")
        self.assertNotEqual(EmailTemplate.objects.get(key="session_reminder", language="en-us").body, "{% if %}")

    def test_write_a_missing_language_starting_from_english(self):
        EmailTemplate.objects.filter(key="campaign_girlz", language="fr-be").delete()
        response = self.client.get(self._edit("campaign_girlz", "fr-be"))
        self.assertContains(response, "no Français version yet")
        self.assertEqual(
            response.context["form"]["subject"].value(),
            EmailTemplate.objects.get(key="campaign_girlz", language="en-us").subject,
        )
        self.client.post(
            self._edit("campaign_girlz", "fr-be"), {"subject": "CoderDojo Girlz", "body": "Salut !", "description": ""}
        )
        self.assertTrue(EmailTemplate.objects.filter(key="campaign_girlz", language="fr-be").exists())

    def test_create_a_campaign_template(self):
        response = self.client.post(
            reverse("manage_template_create"), {"key": "campaign_summer", "category": "newsletter", "description": ""}
        )
        self.assertRedirects(response, self._edit("campaign_summer"))
        self.assertEqual(EmailTemplate.objects.get(key="campaign_summer").language, "en-us")
        response = self.client.post(
            reverse("manage_template_create"), {"key": "campaign_summer", "category": "newsletter", "description": ""}
        )
        self.assertContains(response, "already exists")

    def test_what_can_and_can_not_be_deleted(self):
        delete_key = lambda key: reverse("manage_template_delete", kwargs={"key": key})  # noqa: E731
        delete_language = lambda key, lang: reverse(  # noqa: E731
            "manage_template_delete_language", kwargs={"key": key, "language": lang}
        )

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


class OrganisationEventsInDigestTests(TestCase):
    def test_the_new_sessions_digest_skips_the_organisations_own_events(self):
        from .automated import announce_new_sessions

        org = make_dojo("CoderDojo Belgium", kind=Dojo.ORGANISATION)
        parent = User.objects.create(username="p", email="p@example.com")
        Guardianship.objects.create(guardian=parent, ninja=Ninja.objects.create(name="Kid", home_dojo=org))
        start = timezone.now() + timedelta(days=10)
        Event.objects.create(
            name="Girlz", dojo=org, status=Event.OPEN, places=10, start_time=start, end_time=start + timedelta(hours=2)
        )
        self.assertEqual(announce_new_sessions(), 0)
        self.assertFalse(EmailMessage.objects.filter(template_key="new_sessions_at_dojo").exists())

    def test_near_dojo_does_not_offer_organisation_dojos(self):
        from django.contrib.gis.geos import Point

        from campaigns.segmentation.registry import get_attribute

        make_dojo("CoderDojo Belgium", kind=Dojo.ORGANISATION, location=Point(4.35, 50.85, srid=4326))
        ghent = make_dojo("Ghent", location=Point(3.72, 51.05, srid=4326))
        self.assertEqual([c.value for c in get_attribute("near_dojo").choices()], [ghent.pk])


# --- the mail queue on the organisation dashboard -----------------------------------


class MailQueueDashboardTests(TestCase):
    def setUp(self):
        from accounts.models import OrganisationRole

        self.admin = User.objects.create(username="orgadmin", email="ann@example.com")
        OrganisationRole.objects.create(account=self.admin, role=OrganisationRole.ADMIN)
        self.url = reverse("manage_mail_queue")
        self.client.force_login(self.admin)

    def _mail(self, recipient, subject, status=EmailMessage.Status.PENDING, **fields):
        return EmailMessage.objects.create(
            category=MailCategory.SERVICE, recipient=recipient, subject=subject, body="…", status=status, **fields
        )

    def test_only_the_communication_area_gets_in(self):
        from accounts.models import OrganisationRole

        self.client.logout()
        self.assertEqual(self.client.get(self.url).status_code, 302)  # to login
        board = User.objects.create(username="board", email="bo@example.com")
        OrganisationRole.objects.create(account=board, role=OrganisationRole.BOARD)
        family = make_family("fam", Ninja.GIRL)
        for user in (board, family):
            self.client.force_login(user)
            self.assertEqual(self.client.get(self.url).status_code, 404)
        self.client.force_login(self.admin)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "mailing/manage/mail_queue.html")
        self.assertContains(response, f'href="{self.url}"')  # the sidebar link

    def test_shows_what_waits_failed_bounced_and_is_blocked(self):
        waiting = self._mail("wait@example.com", "Waiting mail")
        self._mail("busy@example.com", "Being sent", status=EmailMessage.Status.SENDING)
        self._mail("done@example.com", "Already sent", status=EmailMessage.Status.SENT, sent_at=timezone.now())
        self._mail(
            "bad@example.com", "Refused mail", status=EmailMessage.Status.FAILED, status_reason="550 no such user"
        )
        BounceRecord.objects.create(
            email="gone@example.com",
            kind=BounceRecord.HARD,
            status_code="5.1.1",
            diagnostic="mailbox unknown",
            message=waiting,
        )
        EmailSuppression.objects.create(email="blocked@example.com", reason=EmailSuppression.COMPLAINT)

        response = self.client.get(self.url)
        for text in ("Waiting mail", "Being sent", "Refused mail", "550 no such user", "gone@example.com", "5.1.1"):
            self.assertContains(response, text)
        self.assertContains(response, "blocked@example.com")
        self.assertNotContains(response, "Already sent")
        counts = response.context["counts"]
        self.assertEqual(
            (
                counts["pending"],
                counts["sending"],
                counts["sent_today"],
                counts["failed"],
                counts["bounces"],
                counts["blocked"],
            ),
            (1, 1, 1, 1, 1, 1),
        )
        self.assertFalse(response.context["stalled"])

    def test_scheduled_mail_is_counted_apart_and_never_looks_stalled(self):
        mail = self._mail("later@example.com", "Later", send_after=timezone.now() + timedelta(days=1))
        EmailMessage.objects.filter(pk=mail.pk).update(created_at=timezone.now() - timedelta(hours=3))
        response = self.client.get(self.url)
        self.assertEqual((response.context["counts"]["pending"], response.context["counts"]["scheduled"]), (0, 1))
        self.assertFalse(response.context["stalled"])

    def test_warns_when_due_mail_has_waited_too_long(self):
        mail = self._mail("stuck@example.com", "Stuck")
        EmailMessage.objects.filter(pk=mail.pk).update(created_at=timezone.now() - timedelta(hours=1))
        response = self.client.get(self.url)
        self.assertTrue(response.context["stalled"])
        self.assertContains(response, "Mail isn't going out.")

    def test_old_failures_and_bounces_drop_off(self):
        old = timezone.now() - timedelta(days=40)
        mail = self._mail("old@example.com", "Old failure", status=EmailMessage.Status.FAILED)
        EmailMessage.objects.filter(pk=mail.pk).update(created_at=old)
        bounce = BounceRecord.objects.create(email="oldbounce@example.com", kind=BounceRecord.SOFT)
        BounceRecord.objects.filter(pk=bounce.pk).update(created_at=old)
        response = self.client.get(self.url)
        self.assertNotContains(response, "Old failure")
        self.assertNotContains(response, "oldbounce@example.com")

    def test_search_narrows_every_section_to_one_address(self):
        self._mail("ann@example.com", "For Ann")
        self._mail("bob@example.com", "For Bob")
        BounceRecord.objects.create(email="bob@example.com", kind=BounceRecord.SOFT)
        EmailSuppression.objects.create(email="bob-old@example.com", reason=EmailSuppression.MANUAL)
        response = self.client.get(self.url, {"q": "ann@"})
        self.assertContains(response, "For Ann")
        self.assertNotContains(response, "For Bob")
        self.assertNotContains(response, "bob@example.com")
        self.assertNotContains(response, "bob-old@example.com")


# --- §25 phase 1: muting one dojo's news ----------------------------------------


class DojoMailMuteTests(TestCase):
    """A family can stop one dojo's `dojo_news` mail and keep the others'
    (DATA_MODEL.md §25)."""

    def setUp(self):
        from .preferences import set_dojo_mute

        self.set_dojo_mute = set_dojo_mute
        EmailTemplate.objects.create(
            key="dojo_note",
            language="en-us",
            category=MailCategory.DOJO_NEWS,
            subject="News",
            body="News. {{ unsubscribe_url }}",
        )
        self.ghent, self.antwerp = make_dojo("Ghent"), make_dojo("Antwerp")
        self.parent = User.objects.create(username="parent", email="p@example.com")
        self.kid = Ninja.objects.create(name="Emma", home_dojo=self.ghent)
        Guardianship.objects.create(guardian=self.parent, ninja=self.kid)

    def _news(self, dojo, **kwargs):
        return send(self.parent, MailCategory.DOJO_NEWS, "dojo_note", dojo=dojo, **kwargs)

    def test_muting_logs_consent_once_and_unmuting_logs_again(self):
        self.assertTrue(self.set_dojo_mute(self.parent, self.ghent, True, ConsentEvent.PREFERENCES))
        self.assertFalse(self.set_dojo_mute(self.parent, self.ghent, True, ConsentEvent.PREFERENCES))
        self.assertTrue(self.set_dojo_mute(self.parent, self.ghent, False, ConsentEvent.PREFERENCES))
        events = list(ConsentEvent.objects.order_by("id").values_list("category", "dojo", "subscribed"))
        self.assertEqual(
            events,
            [(MailCategory.DOJO_NEWS, self.ghent.pk, False), (MailCategory.DOJO_NEWS, self.ghent.pk, True)],
        )

    def test_a_muted_dojos_news_is_suppressed_and_other_dojos_still_come(self):
        self.set_dojo_mute(self.parent, self.ghent, True, ConsentEvent.PREFERENCES)
        muted, other = self._news(self.ghent), self._news(self.antwerp)
        self.assertEqual(
            (muted.status, muted.status_reason), (Status.SUPPRESSED, "The recipient muted this dojo's news.")
        )
        self.assertEqual(muted.dojo, self.ghent)
        self.assertEqual(other.status, Status.PENDING)
        # A test mail skips preferences, the mute included.
        self.assertEqual(self._news(self.ghent, test=True).status, Status.PENDING)

    def test_the_mute_only_applies_to_dojo_news(self):
        EmailTemplate.objects.create(
            key="reminder_note", language="en-us", category=MailCategory.REMINDER, subject="R", body="R"
        )
        self.set_dojo_mute(self.parent, self.ghent, True, ConsentEvent.PREFERENCES)
        row = send(self.parent, MailCategory.REMINDER, "reminder_note", dojo=self.ghent)
        self.assertEqual(row.status, Status.PENDING)

    def test_muting_after_queuing_stops_it_before_sending(self):
        row = self._news(self.ghent)
        EmailMessage.objects.filter(pk=row.pk).update(status=Status.SENDING, claimed_at=timezone.now())
        self.set_dojo_mute(self.parent, self.ghent, True, ConsentEvent.PREFERENCES)
        connection = FakeConnection()
        with patch("mailing.tasks.mail.get_connection", return_value=connection):
            send_email_batch([row.pk])
        self.assertEqual(connection.sent, [])
        self.assertEqual(EmailMessage.objects.get(pk=row.pk).status, Status.SUPPRESSED)

    def test_the_unsubscribe_link_and_header_carry_the_dojo(self):
        from .services import read_unsubscribe_token

        row = self._news(self.ghent)
        token = re.search(r"/mail/unsubscribe/([^/]+)/", row.body).group(1)
        self.assertEqual(read_unsubscribe_token(token), (self.parent.pk, MailCategory.DOJO_NEWS, self.ghent.pk))
        EmailMessage.objects.filter(pk=row.pk).update(status=Status.SENDING, claimed_at=timezone.now())
        connection = FakeConnection()
        with patch("mailing.tasks.mail.get_connection", return_value=connection):
            send_email_batch([row.pk])
        header = connection.sent[0].extra_headers["List-Unsubscribe"]
        # The token carries a timestamp, so the header's (made when sending) can differ from the body's.
        header_token = re.search(r"/mail/unsubscribe/([^/]+)/", header).group(1)
        self.assertEqual(read_unsubscribe_token(header_token), read_unsubscribe_token(token))

    def test_the_new_sessions_mail_skips_a_family_that_muted_the_dojo(self):
        from .automated import announce_new_sessions

        call_command("load_mail_templates", stdout=StringIO())
        start = timezone.now() + timedelta(days=10)
        Event.objects.create(
            name="Scratch", dojo=self.ghent, status=Event.OPEN, places=5, start_time=start, end_time=start
        )
        self.set_dojo_mute(self.parent, self.ghent, True, ConsentEvent.PREFERENCES)
        self.assertEqual(announce_new_sessions(), 0)
        row = EmailMessage.objects.get(template_key="new_sessions_at_dojo")
        self.assertEqual((row.status, row.dojo), (Status.SUPPRESSED, self.ghent))


class DojoUnsubscribeViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create(username="parent", email="p@example.com")
        self.dojo = make_dojo("Ghent")
        token = unsubscribe_token(self.user, MailCategory.DOJO_NEWS, self.dojo)
        self.url = reverse("mail_unsubscribe", kwargs={"token": token})

    def _muted(self):
        from .preferences import is_dojo_muted

        return is_dojo_muted(self.user, self.dojo)

    def test_get_offers_the_three_choices_and_changes_nothing(self):
        response = self.client.get(self.url)
        self.assertContains(response, 'value="dojo" checked')
        self.assertContains(response, 'value="category"')
        self.assertContains(response, 'value="all"')
        self.assertContains(response, "Ghent")
        self.assertFalse(self._muted())

    def test_one_click_post_mutes_only_that_dojo(self):
        response = Client(enforce_csrf_checks=True).post(self.url, {"List-Unsubscribe": "One-Click"})
        self.assertContains(response, "News from your other dojos still comes")
        self.assertTrue(self._muted())
        self.assertTrue(is_subscribed(self.user, MailCategory.DOJO_NEWS))
        self.assertEqual(ConsentEvent.objects.get().source, ConsentEvent.UNSUBSCRIBE_LINK)

    def test_every_dojos_news(self):
        self.client.post(self.url, {"scope": "category"})
        self.assertFalse(is_subscribed(self.user, MailCategory.DOJO_NEWS))
        self.assertFalse(self._muted())
        self.assertTrue(is_subscribed(self.user, MailCategory.REMINDER))

    def test_everything_optional(self):
        self.client.post(self.url, {"scope": "all"})
        self.assertFalse(is_subscribed(self.user, MailCategory.REMINDER))

    def test_a_deleted_dojo_falls_back_to_the_category(self):
        self.dojo.delete()
        response = self.client.get(self.url)
        self.assertNotContains(response, 'value="dojo"')
        self.client.post(self.url)
        self.assertFalse(is_subscribed(self.user, MailCategory.DOJO_NEWS))


class MailPreferencesDojoTests(TestCase):
    def setUp(self):
        self.parent = User.objects.create(username="parent", email="p@example.com")
        self.ghent, self.antwerp, self.bruges = make_dojo("Ghent"), make_dojo("Antwerp"), make_dojo("Bruges")
        kid = Ninja.objects.create(name="Emma", home_dojo=self.ghent)
        Guardianship.objects.create(guardian=self.parent, ninja=kid)
        # A visit to Antwerp last month makes it one of the family's dojos too.
        start = timezone.now() - timedelta(days=30)
        visit = Event.objects.create(
            name="Visit", dojo=self.antwerp, status=Event.CLOSED, places=5, start_time=start, end_time=start
        )
        Registration.objects.create(event=visit, ninja=kid, waiting_list=False, position=1, attended=True)
        self.client.force_login(self.parent)

    def _post(self, **dojos):
        data = {"category_dojo_news": "on", "category_reminder": "on", "preferred_language": "en-us"}
        data.update({f"dojo_{pk}": "on" for pk in dojos.values()})
        return self.client.post(reverse("mail_preferences"), data)

    def test_lists_the_familys_dojos_switched_on(self):
        form = self.client.get(reverse("mail_preferences")).context["form"]
        self.assertEqual([d.name for d in form.dojos], ["Antwerp", "Ghent"])
        self.assertTrue(all(field.value() for field in form.dojo_fields()))

    def test_switching_one_off_mutes_it_and_it_stays_listed(self):
        from .preferences import muted_dojo_ids

        self.assertRedirects(self._post(ghent=self.ghent.pk), reverse("mail_preferences"))
        self.assertEqual(muted_dojo_ids(self.parent), {self.antwerp.pk})
        self.assertTrue(is_subscribed(self.parent, MailCategory.DOJO_NEWS))
        # Even once the visit is too long ago, a muted dojo stays listed to switch back on.
        Registration.objects.all().delete()
        form = self.client.get(reverse("mail_preferences")).context["form"]
        self.assertEqual([d.name for d in form.dojos], ["Antwerp", "Ghent"])
        self.assertFalse(form[f"dojo_{self.antwerp.pk}"].value())
        self._post(ghent=self.ghent.pk, antwerp=self.antwerp.pk)
        self.assertEqual(muted_dojo_ids(self.parent), set())

    def test_an_account_without_children_has_no_dojo_switches(self):
        self.client.force_login(User.objects.create(username="solo", email="s@example.com"))
        self.assertNotContains(self.client.get(reverse("mail_preferences")), "Your dojos")

    def test_a_ninja_login_sees_its_own_dojo(self):
        teen = User.objects.create(username="teen", email="t@example.com", account_type=User.NINJA)
        Ninja.objects.create(name="Teen", home_dojo=self.bruges, account=teen)
        self.client.force_login(teen)
        form = self.client.get(reverse("mail_preferences")).context["form"]
        self.assertEqual([d.name for d in form.dojos], ["Bruges"])


# --- §25 phases 2 and 3: a dojo's audiences and its mailings --------------------


# --- §25 phase 4: the dojo's Mail pages ------------------------------------------


# --- §25 phase 5: the organisation sees every dojo's mail --------------------------


class PrivacyExplanationTests(TestCase):
    def test_it_says_the_dojo_can_write_and_has_a_new_version(self):
        user = User.objects.create(username="parent", email="p@example.com")
        self.client.force_login(user)
        response = self.client.get(reverse("mail_preferences"))
        self.assertContains(response, "The team of the dojo your child goes to can also write to you")
        self.assertEqual(PRIVACY_WORDING_VERSION, "2026-09-29")
