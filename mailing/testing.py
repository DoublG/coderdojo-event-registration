"""Test helpers for mail: realistic bounce reports (also for `manage.py
simulate_bounce`), a family with children and a stand-in SMTP connection.
Used by the mailing and campaigns tests; not imported by the site itself."""

from django.conf import settings

from accounts.consent import consent_fields
from accounts.models import Guardianship, Ninja, User


def _bounce_address():
    return (settings.MAILING_BOUNCE_ADDRESS or "bounces@example.org").replace("{id}", "0")


def dsn_report(
    recipient, message_id="", action="failed", status="5.1.1", to=None, diagnostic="smtp; 550 5.1.1 No such user"
):
    """A delivery-status notification (RFC 3464), as a receiving server sends
    it back: action `failed` + 5.x.x is a hard bounce, `delayed` a soft one."""
    original = (
        f"Message-ID: {message_id}\nSubject: (original message)\n" if message_id else "Subject: (original message)\n"
    )
    return f"""From: MAILER-DAEMON@mx.example.net
To: {to or _bounce_address()}
Subject: Undelivered Mail Returned to Sender
Message-ID: <dsn-{abs(hash((recipient, message_id, action)))}@mx.example.net>
MIME-Version: 1.0
Content-Type: multipart/report; report-type=delivery-status; boundary="B"

--B
Content-Type: text/plain

This is the mail system. Your message could not be delivered.

--B
Content-Type: message/delivery-status

Reporting-MTA: dns; mx.example.net

Final-Recipient: rfc822; {recipient}
Action: {action}
Status: {status}
Diagnostic-Code: {diagnostic}

--B
Content-Type: text/rfc822-headers

{original}
--B--
""".encode()


def complaint_report(recipient, message_id=""):
    """A spam complaint as a mailbox provider's feedback loop sends it (ARF,
    RFC 5965)."""
    return f"""From: feedback@provider.example
To: {_bounce_address()}
Subject: Complaint about message
MIME-Version: 1.0
Content-Type: multipart/report; report-type=feedback-report; boundary="F"

--F
Content-Type: text/plain

This is an email abuse report.

--F
Content-Type: message/feedback-report

Feedback-Type: abuse
Original-Rcpt-To: {recipient}

--F
Content-Type: text/rfc822-headers

Message-ID: {message_id}

--F--
""".encode()


def make_family(username, *genders, consent=True, **fields):
    """An adult account with one child per gender given; by default the
    parent agreed to the children's details choosing their mail
    (accounts.consent), as child groups in segments need."""
    fields.setdefault("email", f"{username}@example.com")
    guardian = User.objects.create(username=username, **fields)
    for index, gender in enumerate(genders):
        ninja = Ninja.objects.create(name=f"{username}-kid-{index}", gender=gender)
        Guardianship.objects.create(guardian=guardian, ninja=ninja, **consent_fields(consent))
    return guardian


class FakeConnection:
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
