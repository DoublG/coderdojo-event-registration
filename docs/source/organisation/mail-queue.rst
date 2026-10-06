Mail queue and mail log
=======================

Every mail the site sends, from a booking confirmation to a campaign, first
waits in a queue and goes out within a minute or so. **Mail queue** (under
**Communication**) shows that queue, so you can check that mail is going
out, see what went wrong for someone who says they got nothing, send failed
mail again and unblock an address. **Mail log**, right under it, lists every
mail the site sent.

At the top are the numbers: mail waiting to be sent, being sent right now,
scheduled for later, sent in the last 24 hours, and failed mail, bounces
and blocked addresses.

If mail that should have gone out has been waiting for more than half an
hour, the page says **Mail isn't going out**. The programs that send the
mail have probably stopped; ask whoever runs the server to check them.
Nothing is lost: the waiting mail goes out as soon as they run again.

To look up one person, type (part of) their email address in the search box:
every section then only shows mail for that address.

The sections
------------

- **Waiting to be sent**: mail in the queue, in the order it goes out.
  Account and booking mail goes before campaigns, so a big campaign never
  holds up a booking confirmation. **Not before** is set for mail that's
  scheduled for later.
- **Failed**: mail from the last 30 days that the mail server refused, or
  that still couldn't be sent after several tries, with the reason.
- **Bounces and complaints**: mail from the last 30 days that came back from
  the recipient's mail server (for example because the address doesn't
  exist), or that the recipient marked as spam. A *hard bounce* (the address
  doesn't work) or a complaint stops all mail to that address straight
  away; a *soft bounce* (a full mailbox, a server that's down for a while)
  only does after it happens a few times.
- **Blocked addresses**: addresses nothing is sent to any more, whatever the
  person chose on their **Mail preferences** page, with the reason.

Sending failed mail again
-------------------------

Once the problem is fixed (the mail server works again, or a typo in an
address was corrected on the account), click **Send again** next to a failed
mail, or **Send all again** above the list to send every failed mail shown
(only the ones for the address you searched for, if you searched). The mail
goes back in the queue and out within a minute or so. Just before it goes,
the site checks again that the person still wants that kind of mail and that
the address isn't blocked, as it does for every mail.

A mail can't be sent again when its address is blocked (unblock it first),
or when it's more than a year old: by then its address, subject and text
have been cleared.

Blocking an address
-------------------

When someone asks us to stop sending them anything at all, or an address
must not be mailed, fill in **Block an address** under **Blocked
addresses**: the address, and why (only the organisation sees the note).
From then on nothing is sent there, whatever the person chose on their
**Mail preferences** page, and mail still waiting to go to that address is
withdrawn. Who blocked an address is recorded in the audit log. To let mail
go there again, unblock it (below).

Unblocking an address
---------------------

Click **Unblock** next to a blocked address once it works again, for
example after the person fixed their mailbox. Mail goes there again from
then on; the person's own choices on their **Mail preferences** page stay
as they are. Be careful with a *spam complaint*: the person told their mail
provider they don't want our mail, so unblock it only if they asked you to.
Who unblocked an address is recorded in the audit log.

The mail log
------------

**Mail log** lists every mail the site queued, newest first: who it went
to, the subject, what kind of mail it is, whether it went out (and why not)
and when. Search for an email address or a subject, or show only one status
or kind of mail, to answer "did they get our mail?". A failed mail has a
**Send again** button here too.

The text of a mail isn't shown: some mails hold a personal login or
password link, which would let whoever reads it log in as that person. If
you need the full text, it's in the Django admin, which you ask for when you
need it (see :doc:`django-admin`).

A year after a mail was queued, its address, subject and text are cleared;
the row stays, without them, for the figures.
