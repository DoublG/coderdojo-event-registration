# 31. Telling families about a change to their session (not built — written up for review)

> Split out of [`DATA_MODEL.md`](DATA_MODEL.md) like §11, §25 and §30. Written 5 November 2026 for
> review before anything is built. Decided the same day: decisions 3 and 7 and the related fix on the
> places (who sends, a real cancelled status, raising the places promotes the waiting list); the rest
> are proposals until the open points at the end are settled.

## What it's for

A dojo's team changes a session that families already booked: it moves to another room or building,
starts later, gets more or fewer places, or is called off. Today the families only find out if they
look at the session's page again. This feature lets whoever changed the session mail **every family
with a place, on the waiting list, or both**, from a set of prepared mails (venue changed, times
changed, places changed, cancelled) or with a text of their own, in each family's own language.

## What's already there (and what it means for the design)

- **Editing a session** is `dojos.views.event_pages.dojo_event_detail` (`EventForm`, capability
  `MANAGE_EVENTS`: the champion and the mentors). Status is set apart from the form, by
  `dojo_event_set_status` → `events.services.set_status`. Saving the form says nothing to anyone.
- **The dojo's own mail** (§25, `campaigns/dojo_views.py`) already has a "Families booked for a
  session" audience, with or without the waiting list. It isn't the right tool here: it's `dojo_news`
  (families can switch it off, or mute the dojo), champion only (`SEND_MAIL`), at most
  `MAILING_DOJO_MAILINGS_PER_30_DAYS` = 4, and it goes through a draft → launch flow meant for news,
  not for "your session tomorrow moved".
- **The booking mails** (`mailing/automated.py`: `booking_mail`, `waitlist_promoted_mail`,
  `send_session_reminders`) are `registration`/`reminder` mail sent with `send()` per family
  (`family_of(ninja)`: every guardian plus the child's own login with an email), each with an
  idempotency key. A change notice belongs with these: it's about a booking the family made.
- **There is no cancelled session.** `Event.status` is draft/open/closed. Closing a session leaves it
  visible (`Event.objects.visible()` includes closed), so the reminder two days before still goes out
  (`send_session_reminders` reads `visible()`), and the engagement snapshot counts it as a session the
  child was offered and missed (`events/engagement.py` excludes only drafts). Calling a session off by
  closing it would mail a reminder for a session that won't happen and mark every booked child "missed".
- **Raising the places doesn't move anyone off the waiting list.** Only a cancelled place promotes
  (`events.registrations.cancel`). So after "we found room for 5 more" the waiting list stays exactly
  where it was, which a "places changed" mail would contradict.

## Proposed decisions

1. **Its own mail category's rules, not a campaign.** Each notice is sent with `send()` per account, as
   `registration` mail (can't be switched off, isn't muted with the dojo, doesn't count towards the four
   dojo mailings), from a new service `events/notices.py`, like the other booking mails. No `Campaign`
   row: there's no draft, schedule or segment, and the audience is simply the session's registrations at
   the moment of sending.
2. **One record per notice sent**, `events.SessionNotice` (below), so the session's page can show what
   was already sent, the idempotency keys have something to hang on, and the organisation can see it.
3. **Who can send: whoever can change the session** (`MANAGE_EVENTS`, champion and mentors; decided
   5 Nov 2026). The notice is part of changing the session. Abuse is limited by the rules in decision 8,
   and every notice is visible to the dojo's team and the organisation.
4. **Five kinds**, each a system mail template in en/nl/fr (`mailing/seed_templates.py`,
   `SYSTEM_TEMPLATE_KEYS`), with the session's details filled in by the site and an optional note from
   the team (inserted as a variable, never rendered as template code, as `dojo_message` does):

   | Kind | Template key | Filled in by the site | Default audience |
   |---|---|---|---|
   | Venue changed | `session_venue_changed` | old venue → new venue, date and times | place + waiting list |
   | Times changed | `session_time_changed` | old date/times → new ones, venue | place + waiting list |
   | Places changed | `session_places_changed` | old → new number of places, the child's status now | waiting list |
   | Cancelled | `session_cancelled` | the session, "your place is released" | place + waiting list |
   | Message | `session_message` | only the frame (greeting, session, footer); subject and text from the team | place + waiting list |

   Every mail names the session, its dojo, the child or children it's about, and links to the session's
   page; Reply-To is the dojo's email address (as §25), so a family can answer the team.
5. **Offered after saving, and always reachable.** When a save of an **open** session that hasn't
   ended changes the venue, the date or times, or the places, and the session has registrations, the
   "Saved" banner becomes "You changed the venue. Let the 14 families know?" with a button to the
   compose page, the kind picked and the old values carried along. Besides that, the session's page
   gets a **Mail the families** card (open or closed, not yet ended, at least one registration) for the
   free text and for anything the team wants to say later. Nothing is ever sent without the team
   pressing Send on the compose page.
6. **The old values travel signed.** The banner's link carries the before-values (venue, start, end,
   places) in a `django.core.signing` token (salt `events.notice`, an hour), so the compose page can say
   "moved from Room 1 to the library" without a model of pending changes. Opened without a token (the
   card), the kinds that need a before-value ask for it on the form, prefilled with today's values.
7. **Cancelling is a status** (decided 5 Nov 2026), `Event.CANCELLED`, set from the status card with a confirmation that is
   also the compose page for `session_cancelled` (the team can add a note; sending is ticked by default
   when there are registrations, and can be switched off). A cancelled session:
   - stays visible on the dojo's page and the session's page, marked *Cancelled*, with no sign-up;
   - is left out of the upcoming lists, the carousel, the dojo finder's next session and the new-sessions
     announcement (`visible()` keeps it, a new `bookable()` or the existing upcoming queries exclude it);
   - gets no reminder (`send_session_reminders` skips it) and doesn't count as offered in the engagement
     snapshot (`events/engagement.py` treats it like a draft);
   - keeps its registrations (history; nobody's place is deleted), but they don't count as missed;
   - can be reopened (any status to any other, as today), which offers a "Message" notice.
8. **Guardrails.** At most `SESSION_NOTICES_PER_DAY` (proposed 3) notices per session per day; a free
   text of at most 2,000 characters; no notice for a session that ended more than a day ago; the
   compose page shows the count of accounts it reaches and a preview in the team's language before Send.
9. **One mail per account per notice.** A parent with two children on the same session gets one mail
   naming both. Idempotency key `session_notice:<notice id>:<user id>`, so a retry or double click
   never mails anyone twice. A child's own login gets it like the other booking mails.
10. **Languages.** The site's part is the template in the recipient's `preferred_language`; the team's
    note and the free text's subject and text are a `TranslatableModel` in the dojo's languages (§19),
    entered like a dojo mailing's (`add_translation_fields`), falling back to the main language.

## Model

`events.SessionNotice` (append-only):

| Field | Type | Notes |
|---|---|---|
| `event` | FK `Event`, cascade | |
| `kind` | choice | `venue_changed`, `time_changed`, `places_changed`, `cancelled`, `message` |
| `audience` | choice | `confirmed`, `waiting_list`, `both` |
| `subject`, `note` | text | the team's own text (subject only for `message`); `TRANSLATABLE_FIELDS`, `translations` JSON |
| `changes` | JSON | the before/after values shown in the mail (`{"venue": ["Room 1", "Library"]}`), not personal |
| `sent_by` | FK `User`, set null | who pressed Send |
| `sent_at` | datetime | |
| `recipients` | int | accounts mailed (after suppression and inactive accounts) |

Privacy registry: `sent_by` personal (identity, `export=False` for the families, it's someone else),
`subject`/`note` personal (free text can name anyone; emptied with the dojo team member's erasure only
if we decide so, open point 1), the rest not personal; `subjects` for the sender's own export. Audit
log: not recorded (it is itself a record of what was sent; `core.tests.AuditLogCoverageTests.NOT_RECORDED`
with that reason). Retention: with the session (`team`/`registration` history rule), or a period of its
own. The mails themselves are `EmailMessage` rows, cleared after `MAIL_CONTENT_RETENTION_DAYS` as now.

`Event.status` gains `cancelled` (a migration, and `STATUS_CHOICES`), and the status card, the events
list, the public event page, the API's event sync (a synced row never cancels or un-cancels; open
point 2) and `DATA_MODEL.md`'s event state machine follow.

## Pages

- `dojos/<id>/events/<event_id>/notify/` (`dojo_event_notify`, `MANAGE_EVENTS`): GET the compose page
  (kind, audience, before-values when needed, note or subject + text per dojo language, the reach,
  a preview), POST sends through `events.notices.send_notice` and goes back to the session's page with
  "Mailed 14 families". A `?change=<token>` from the save banner prefills it.
- The session's page: the *Mail the families* card, and a *Sent to families* list of its notices
  (kind, when, by whom, how many).
- The status card: *Cancel session…* opens the cancellation's confirm/compose page
  (`dojo_event_cancel`).
- The organisation sees the notices on the dojo's sessions in its Mail log (they're ordinary
  `EmailMessage` rows with the template key); a page of its own is not planned.

## Service

`events/notices.py` (typed, joins `[tool.mypy] files`):

- `recipients(event, audience) -> list[tuple[User, list[Ninja]]]`: the families of the session's
  registrations (`family_of`), one entry per account with its children.
- `notice_problems(event, kind, audience, ...) -> dict[str, str]`: the guardrails above, as form errors.
- `send_notice(event, kind, audience, *, sent_by, note=..., changes=...) -> SessionNotice` in one
  transaction: checks, writes the `SessionNotice`, calls `send()` per account (`registration`, the dojo
  as Reply-To and From name, the idempotency key). Raises `NoticeError` with a user-facing message.
- `change_token(event, before) / read_change_token(token)`: the signed before-values.
- `cancel(event, *, cancelled_by, notify, note)` in `events.services` next to `set_status`, which sets
  `cancelled` and sends the notice when asked.

## Related fix, built first: raising the places (decided and built 5 Nov 2026)

Since raising `places` leaves the waiting list where it is, saving more places promotes
the children waiting longest into the new places, through `events.registrations` (locked like
`cancel`), each family getting the existing `waitlist_promoted_mail`. The "places changed" notice is
then about what the change means for everyone else (still waiting, or fewer places). Without that fix
the kind would mislead the waiting list. Lowering the places never removes a child who has one.

## Tests (per CLAUDE.md, "New features need tests")

`events.tests`: `send_notice` reaches exactly the right accounts per audience, one mail per account
with several children, a ninja's own login, idempotent on a repeat, the daily limit, an ended session,
a suppressed address; `cancel` keeps registrations, stops the reminder, and leaves the engagement
snapshot alone; the token round-trip and a tampered token. `dojos.tests`: the compose page's access
(champion, mentor, youth mentor 404, another dojo 404), the banner appearing only for an open session
with registrations and a watched field changed, POST effect. `mailing.tests`: every new template renders
in all three languages with its `SAMPLE_CONTEXT`. Plus the guard tests a new model touches (privacy
classification, export coverage, audit-log decision, admin stays usable, `__str__` never queries, the
form's translated labels).

## Also to update when it's built

The help centre (the dojo team's page on sessions, en/fr/nl), `DATA_MODEL.md`'s event state machine,
`mailing/CLAUDE.md`'s automated mail list, the dojo-team user-journey PDFs (`check_journeys.py`), and
`seed_mailing`/`seed_templates` for the five templates.

## Phases

1. Raising places promotes the waiting list (the related fix), on its own. **Built 5 Nov 2026:**
   `events.registrations.fill_free_places`, called by the event page (`dojo_event_detail`, with a note
   on how many moved up) and the API's sync when the places go up.
2. `SessionNotice`, `events/notices.py`, the five templates, the compose page and the *Mail the families*
   card (all kinds except cancelled). **Built 5 Nov 2026:** `events.SessionNotice`, `events/notices.py`
   (`recipients`, `reach`, `notice_problems`, `send_notice`, `preview`, the change token), the templates
   `session_venue_changed`, `session_time_changed`, `session_places_changed`, `session_cancelled` and
   `session_message` (`mailing/seed_templates.py`), `events.forms.SessionNoticeForm`, the compose page
   `dojos.views.notices.dojo_event_notify` (`/dojos/<id>/events/<event_id>/notify/`, with a *Preview*
   before *Send*) and the card on the session's page (`dojos/partials/_event_notices.html`). Settings:
   `SESSION_NOTICES_PER_DAY` (3, any 24 hours), `SESSION_NOTICE_MAX_LENGTH` (2,000),
   `SESSION_NOTICE_HOURS_AFTER_END` (24).
3. The save banner with the signed before-values. **Built 5 Nov 2026, with phase 2:** a save of an open
   session with registrations that changed the venue, times or places turns the card into a button per
   change; a change the families were already mailed about (a notice of that kind with the same
   before/after values) isn't offered again.
4. `Event.CANCELLED`: the status, everything that must skip it, the cancel page with its notice.
   **Built 5 Nov 2026:** `Event.CANCELLED` and `Event.NOT_HELD`, `EventQuerySet.listed()` (lists,
   finder, a dojo's next session, promotions, reminders) and `held()` (engagement, the year's figures,
   the activity segments), `events.services.cancel` (the only way in; `set_status` refuses it and the
   API's sync can't set it and leaves a cancelled session alone, so open point 2 is settled that way),
   the cancellation mail exempt from the daily limit, the Cancel page
   (`/dojos/<id>/events/<event_id>/cancel/`), and *Cancelled* on the public page and the family's
   pages. Help centre: `dojo-team/running-a-session.rst` (places, status, "Mailing the families of a
   session") and `families/signing-up-for-a-session.rst`, `families/mail-preferences.rst`.

## Open points

Decided 5 November 2026: who sends (`MANAGE_EVENTS`), a real `cancelled` status, and raising the places
promotes the waiting list. Still open:

1. The team's free text in `SessionNotice`: keep it with the session, or give it a retention period?
2. ~~The API's event sync and a cancelled session~~ — built as proposed: the sync leaves a cancelled
   session alone (`skipped`) and can't cancel one; say if the spreadsheet should be able to.
3. Should the organisation be able to send a notice for a dojo's session (it can't edit those today)?
