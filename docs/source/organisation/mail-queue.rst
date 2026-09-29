Mail queue
==========

Every mail the site sends, from a booking confirmation to a campaign, first
waits in a queue and goes out within a minute or so. **Mail queue** (under
**Communication**) shows that queue, so you can check that mail is going
out and see what went wrong for someone who says they got nothing. The page
only shows; it doesn't change anything.

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

Fixing something
----------------

Sending a failed mail again, or unblocking an address (for example after
the person fixed their mailbox), is done in the Django admin, which you ask
for when you need it (see :doc:`django-admin`).
