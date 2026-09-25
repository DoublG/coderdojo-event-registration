"""Realistic bounce reports, for the tests and `manage.py simulate_bounce`.
Not imported by the site itself."""

from django.conf import settings


def _bounce_address():
    return (settings.MAILING_BOUNCE_ADDRESS or "bounces@example.org").replace("{id}", "0")


def dsn_report(recipient, message_id="", action="failed", status="5.1.1", to=None,
               diagnostic="smtp; 550 5.1.1 No such user"):
    """A delivery-status notification (RFC 3464), as a receiving server sends
    it back: action `failed` + 5.x.x is a hard bounce, `delayed` a soft one."""
    original = f"Message-ID: {message_id}\nSubject: (original message)\n" if message_id else "Subject: (original message)\n"
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
