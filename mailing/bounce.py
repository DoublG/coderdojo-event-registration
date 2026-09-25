"""Reading bounces and complaints from the bounce mailbox over IMAP
(DATA_MODEL.md §11, "Sending pipeline" step 4).

Every mail goes out with the bounce mailbox as its envelope sender
(settings.MAILING_BOUNCE_ADDRESS), so delivery failures come back there.
process_bounces (beat, every 5 min) runs BounceProcessor().process():

- connect: log in to the mailbox (settings.MAILING_BOUNCE_*): IMAP in
  production, POP3 in the devcontainer, where Mailpit is the mailbox.
- get_new_messages: the messages not handled yet. ProcessedImapMessage
  remembers each one per mailbox (and IMAP UIDVALIDITY), so none is handled
  twice.
- parse: a standard delivery-status report (DSN, RFC 3464) or complaint
  report (ARF, RFC 5965) becomes a Bounce. It's matched to our
  EmailMessage through the VERP address (bounces+<id>@…) or our Message-ID
  in the returned original. Plain-text bounces from older servers are
  recognised when they quote our Message-ID and a status code.
  Auto-replies and anything unrecognised are skipped.
- handle: record a BounceRecord, then
  - hard bounce (5.x.x): mark the mail `bounced`, block the address
  - soft bounce (4.x.x, or delayed): only counted; MAILING_SOFT_BOUNCE_LIMIT
    of them within the window block the address too
  - complaint: switch off every optional category for the account (the
    ConsentEvent source is "bounce"); account and booking mail still go out
"""

import email
import email.policy
import imaplib
import poplib
import re
from dataclasses import dataclass
from datetime import timedelta
from urllib.parse import urlparse

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .categories import CAN_OPT_OUT, categories_for
from .models import BounceRecord, ConsentEvent, EmailMessage, EmailSuppression, ProcessedImapMessage
from .preferences import set_preference

STATUS_CODE_RE = re.compile(r"\b([245])\.(\d{1,3})\.(\d{1,3})\b")
BOUNCE_SUBJECT_RE = re.compile(
    r"undeliver|delivery status notification|delivery failure|failure notice|returned mail|mail delivery failed",
    re.IGNORECASE,
)


@dataclass
class Bounce:
    kind: str  # BounceRecord.HARD / SOFT / COMPLAINT
    email: str
    status_code: str = ""
    diagnostic: str = ""
    message: EmailMessage | None = None


class ImapMailbox:
    """The bounce mailbox, as a context manager. `key` identifies the
    mailbox together with its UIDVALIDITY: when the server renumbers its
    UIDs, the processed-message log starts over instead of skipping mail."""

    def __enter__(self):
        imap_class = imaplib.IMAP4_SSL if settings.MAILING_BOUNCE_IMAP_SSL else imaplib.IMAP4
        self.imap = imap_class(
            settings.MAILING_BOUNCE_IMAP_HOST, settings.MAILING_BOUNCE_IMAP_PORT,
            timeout=settings.MAILING_BOUNCE_IMAP_TIMEOUT,
        )
        self.imap.login(settings.MAILING_BOUNCE_IMAP_USER, settings.MAILING_BOUNCE_IMAP_PASSWORD)
        self.imap.select(settings.MAILING_BOUNCE_IMAP_MAILBOX, readonly=True)
        _typ, data = self.imap.response("UIDVALIDITY")
        uidvalidity = (data[0] or b"0").decode() if data else "0"
        self.key = f"{settings.MAILING_BOUNCE_IMAP_MAILBOX}:{uidvalidity}"
        return self

    def __exit__(self, *exc):
        try:
            self.imap.logout()
        except (imaplib.IMAP4.error, OSError):
            pass
        return False

    def unprocessed_uids(self):
        seen = ProcessedImapMessage.objects.filter(mailbox=self.key).values_list("uid", flat=True)
        return self.uids_after(max((int(uid) for uid in seen), default=0))

    def uids_after(self, last_uid):
        _typ, data = self.imap.uid("SEARCH", None, f"UID {last_uid + 1}:*")
        # "n:*" always matches the newest message, even when its UID is lower.
        return sorted(uid for uid in map(int, (data[0] or b"").split()) if uid > last_uid)

    def fetch(self, uid):
        _typ, data = self.imap.uid("FETCH", str(uid), "(BODY.PEEK[])")
        raw = next(part[1] for part in data if isinstance(part, tuple))
        return email.message_from_bytes(raw, policy=email.policy.default)


class Pop3Mailbox:
    """The bounce mailbox over POP3, for the devcontainer: Mailpit only
    speaks POP3, and every mail it caught is in that one mailbox (anything
    that isn't a bounce is skipped). POP3's unique ids (UIDL) aren't
    ordered, so what's new is whatever hasn't been processed yet. Never
    deletes anything."""

    def __enter__(self):
        pop_class = poplib.POP3_SSL if settings.MAILING_BOUNCE_IMAP_SSL else poplib.POP3
        self.pop = pop_class(settings.MAILING_BOUNCE_IMAP_HOST, settings.MAILING_BOUNCE_IMAP_PORT,
                             timeout=settings.MAILING_BOUNCE_IMAP_TIMEOUT)
        self.pop.user(settings.MAILING_BOUNCE_IMAP_USER)
        self.pop.pass_(settings.MAILING_BOUNCE_IMAP_PASSWORD)
        self.key = f"pop3:{settings.MAILING_BOUNCE_IMAP_HOST}"
        _resp, listing, _octets = self.pop.uidl()
        # "<message number> <unique id>" per message; numbers are only valid
        # for this session, the unique ids are what we remember.
        self.numbers = dict(reversed(line.decode().split(" ", 1)) for line in listing)
        return self

    def __exit__(self, *exc):
        try:
            self.pop.quit()
        except (poplib.error_proto, OSError):
            pass
        return False

    def unprocessed_uids(self):
        seen = set(ProcessedImapMessage.objects.filter(mailbox=self.key, uid__in=list(self.numbers))
                   .values_list("uid", flat=True))
        return [uid for uid in self.numbers if uid not in seen]

    def fetch(self, uid):
        _resp, lines, _octets = self.pop.retr(int(self.numbers[uid]))
        return email.message_from_bytes(b"\r\n".join(lines), policy=email.policy.default)


MAILBOX_CLASSES = {"imap": ImapMailbox, "pop3": Pop3Mailbox}


class BounceProcessor:

    def __init__(self, mailbox_class=None):
        self.mailbox_class = mailbox_class or MAILBOX_CLASSES[settings.MAILING_BOUNCE_PROTOCOL]

    def process(self):
        handled = 0
        with self.connect() as mailbox:
            for uid, message in self.get_new_messages(mailbox):
                with transaction.atomic():
                    _row, new = ProcessedImapMessage.objects.get_or_create(mailbox=mailbox.key, uid=str(uid))
                    if not new:
                        continue
                    bounce = self.parse(message)
                    if bounce:
                        self.handle(bounce)
                handled += 1
        return handled

    def connect(self):
        return self.mailbox_class()

    def get_new_messages(self, mailbox):
        for uid in mailbox.unprocessed_uids()[:settings.MAILING_BOUNCE_BATCH]:
            yield uid, mailbox.fetch(uid)

    # --- parsing -------------------------------------------------------------

    def parse(self, message):
        if self._is_auto_reply(message):
            return None
        ours = self._match_our_message(message)
        report_type = (message.get_param("report-type") or "").lower() if message.get_content_type() == "multipart/report" else ""
        if report_type == "feedback-report":
            return self._parse_complaint(message, ours)
        if report_type == "delivery-status":
            return self._parse_dsn(message, ours)
        return self._parse_plain(message, ours)

    def _is_auto_reply(self, message):
        auto = (message.get("Auto-Submitted") or "").lower()
        return auto.startswith("auto-replied") or bool(message.get("X-Autoreply")) or bool(message.get("X-Autorespond"))

    def _parse_dsn(self, message, ours):
        for part in message.walk():
            if part.get_content_type() != "message/delivery-status":
                continue
            for fields in self._status_blocks(part):
                action = (fields.get("Action") or "").strip().lower()
                status = (fields.get("Status") or "").strip()
                if action not in ("failed", "delayed"):
                    continue
                recipient = self._address(fields.get("Final-Recipient") or fields.get("Original-Recipient"))
                kind = BounceRecord.HARD if action == "failed" and status.startswith("5") else BounceRecord.SOFT
                return self._bounce(kind, recipient, status, fields.get("Diagnostic-Code") or "", ours)
        return None

    def _status_blocks(self, part):
        payload = part.get_payload()
        if isinstance(payload, list):  # the email package splits the report into blocks
            return payload
        text = payload if isinstance(payload, str) else ""
        return [email.message_from_string(block + "\n", policy=email.policy.default) for block in re.split(r"\n\s*\n", text)]

    def _parse_complaint(self, message, ours):
        recipient = ""
        for part in message.walk():
            if part.get_content_type() == "message/feedback-report":
                blocks = self._status_blocks(part)
                recipient = self._address(next((b.get("Original-Rcpt-To") for b in blocks if b.get("Original-Rcpt-To")), ""))
        return self._bounce(BounceRecord.COMPLAINT, recipient, "", "", ours)

    def _parse_plain(self, message, ours):
        """An older server's bounce without a DSN: only when it's clearly a
        bounce (subject), quotes one of our mails and gives a status code."""
        if ours is None or not BOUNCE_SUBJECT_RE.search(message.get("Subject") or ""):
            return None
        match = STATUS_CODE_RE.search(self._text(message))
        if match is None:
            return None
        kind = BounceRecord.HARD if match.group(1) == "5" else BounceRecord.SOFT
        return self._bounce(kind, "", match.group(0), "", ours)

    def _bounce(self, kind, recipient, status, diagnostic, ours):
        address = (recipient or (ours.recipient if ours else "")).strip().lower()
        if not address:
            return None
        return Bounce(kind=kind, email=address, status_code=status[:20], diagnostic=str(diagnostic)[:255], message=ours)

    def _match_our_message(self, message):
        """Our EmailMessage this bounce is about: by the VERP address it was
        sent back to, else by our Message-ID quoted in the returned mail."""
        if "{id}" in settings.MAILING_BOUNCE_ADDRESS:
            prefix, suffix = (re.escape(p) for p in settings.MAILING_BOUNCE_ADDRESS.split("{id}", 1))
            verp = re.compile(prefix + r"(\d+)" + suffix, re.IGNORECASE)
            for header in ("Delivered-To", "X-Original-To", "Envelope-To", "To"):
                for value in message.get_all(header) or []:
                    if (m := verp.search(str(value))) and (row := EmailMessage.objects.filter(pk=int(m.group(1))).first()):
                        return row
        domain = re.escape(urlparse(settings.SITE_URL).hostname or "localhost")
        ids = re.findall(r"<[^<>\s]+@" + domain + ">", self._text(message, include_headers=True))
        return EmailMessage.objects.filter(message_id__in=ids).first() if ids else None

    def _text(self, message, include_headers=False):
        """All text in the message, including the headers of an attached
        original (message/rfc822 or text/rfc822-headers)."""
        chunks = []
        for part in message.walk():
            if include_headers:
                chunks.extend(f"{name}: {value}" for name, value in part.items())
            if part.get_content_maintype() == "text":  # includes text/rfc822-headers
                raw = part.get_payload(decode=True) or b""
                chunks.append(raw.decode(part.get_content_charset() or "utf-8", "replace"))
        return "\n".join(chunks)

    def _address(self, value):
        value = str(value or "")
        return value.split(";", 1)[-1].strip().strip("<>")

    # --- acting on it --------------------------------------------------------

    def handle(self, bounce):
        BounceRecord.objects.create(
            email=bounce.email, kind=bounce.kind, status_code=bounce.status_code,
            diagnostic=bounce.diagnostic, message=bounce.message,
        )
        if bounce.kind == BounceRecord.HARD:
            if bounce.message is not None:
                EmailMessage.objects.filter(pk=bounce.message.pk).update(
                    status=EmailMessage.Status.BOUNCED, bounced_at=timezone.now(),
                    status_reason=f"Bounced {bounce.status_code} {bounce.diagnostic}".strip()[:255],
                )
            self._suppress(bounce.email, EmailSuppression.HARD_BOUNCE, f"{bounce.status_code} {bounce.diagnostic}")
        elif bounce.kind == BounceRecord.SOFT:
            since = timezone.now() - timedelta(days=settings.MAILING_SOFT_BOUNCE_WINDOW_DAYS)
            soft = BounceRecord.objects.filter(email=bounce.email, kind=BounceRecord.SOFT, created_at__gte=since).count()
            if soft >= settings.MAILING_SOFT_BOUNCE_LIMIT:
                self._suppress(bounce.email, EmailSuppression.SOFT_BOUNCES,
                               f"{soft} soft bounces in {settings.MAILING_SOFT_BOUNCE_WINDOW_DAYS} days")
        elif bounce.kind == BounceRecord.COMPLAINT:
            user = bounce.message.user if bounce.message and bounce.message.user_id else None
            if user is None:
                from accounts.models import User

                user = User.objects.filter(email__iexact=bounce.email).first()
            if user is not None:
                for category in categories_for(user):
                    if CAN_OPT_OUT[category]:
                        set_preference(user, category, False, ConsentEvent.BOUNCE)

    def _suppress(self, address, reason, note):
        EmailSuppression.objects.get_or_create(email=address, defaults={"reason": reason, "note": note.strip()[:255]})
