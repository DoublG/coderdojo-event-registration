Planning sessions with your own tools
=====================================

Many dojos plan their whole year at once, for example in a spreadsheet.
Instead of typing every session again on the site, your own tool can put
them on the site through the site's API (see :doc:`api-clients`): a
spreadsheet macro, a script, or anything else that can send a request to
a website. Which tool you use, and how you build it, is up to you. Send
the plan again whenever it changes: the site updates the same sessions,
it never adds them twice.

Only the dojo's **champion** can set this up, because it needs an API
client.

Getting started
---------------

On the dojo's **API** page, add a client (for example "Planning
spreadsheet") and tick only **Plan sessions: add and change them, e.g.
from a spreadsheet**. Give its **client ID** and **client secret** to
whoever builds the tool. The bottom of the **API** page has the addresses
it needs, and the **Reference** link describes every field exactly.

The tool sends your sessions to ``/api/v1/events/sync``, at most 200 per
call. Tools that run in a browser, such as Excel on the web, can call the
API too.

What to send for each session
-----------------------------

==============  ==============================================================
Field           What goes in it
==============  ==============================================================
external_ref    The session's own key: anything that's unique within your
                dojo and **never changes** for that session, for example
                ``2026-W38``. This is how the site recognises the session the
                next time. Change the key and the site sees a new session.
name            The session's name.
date            The day.
start_time      When it starts (14:00).
end_time        When it ends, on the same day.
places          How many children can sign up before new sign-ups go on the
                waiting list; at least 1.
venue_name      Optional. Leave it empty to use the dojo's own address.
min_age         Optional.
max_age         Optional.
audience        Optional: ``everyone`` (when empty) or ``girls``.
status          Optional: ``draft``, ``open`` or ``closed``. A new session
                starts as a draft, hidden from the site, unless you send
                ``open``. Leave it empty to keep the status the session has
                on the site.
==============  ==============================================================

Send every field every time: an empty venue or age also empties it on the
site.

What the site answers
---------------------

For every session it says what happened, and why:

- **created**: a new session, as a draft unless its status says otherwise.
- **updated**: the session changed to match.
- **unchanged**: the session already matched.
- **skipped**: the session has already started, so the site leaves it
  alone. Change it on the site if you need to.
- **error**: this session wasn't saved, for example because the end time
  is before the start time, the day is in the past, or the same key was
  sent twice. The others are saved anyway: fix this one and send it again.

**Sending never deletes a session.** Leaving a session out changes nothing
on the site. To stop a planned session, set its status to ``draft``
(hidden) or ``closed``; to delete it, use the session's page on the site.

The description, the picture, the team and the pathways aren't sent: set
them on the session's page on the site, and the next sync keeps them. A
new session gets the pathways your dojo provides, as it does on the site.

Keep the secret safe
--------------------

Anyone with the client ID and secret can change your dojo's sessions.
Don't save the secret in a file you share, and give this client only
**Plan sessions**, so it can't see who signed up or who came. If the
secret may have leaked, give the client a **New secret** on the **API**
page: the old one stops working at once.
