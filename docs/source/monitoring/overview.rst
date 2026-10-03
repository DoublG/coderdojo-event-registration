Monitoring the site
===================

The site keeps an eye on itself: it counts its visitors, times its pages,
and checks that its database, its cache and the programs that send mail are
working. This section is for whoever looks after the running site (the
organisation's admins and whoever runs the server). It explains where to look,
what the figures mean and when to act. You don't need any of it to use the site.

Nothing the site measures about itself is about a person: the figures are
counts, sizes and times, never names or addresses.

Where to look
-------------

- **The health check** (``/health/``) answers one question: is everything
  working? It checks the database, the cache and the mail workers, and
  answers *ok*, or names the part that isn't working. Point an uptime
  service at it, so someone gets a message when the site is down.
- **The metrics page** (``/metrics/``) lists every figure the site measures,
  in the format monitoring tools read. It's protected by a secret key: only
  a monitoring tool that has it can read the page.
- **The dashboard** (Grafana) draws those figures as charts over time:
  visitors, how fast the pages are, the database, the mail and the memory
  the site uses. On the development site it's at ``/grafana/``; for the live
  site it has to be connected to a monitoring service first.
- **The Mail queue page** on the organisation dashboard shows whether mail
  is going out (see :doc:`../organisation/mail-queue`).
- **A daily sample**: every night at 02:30 the site stores the size of its
  database and its other figures, so growth over months shows up even
  without a monitoring service.

What it measures
----------------

- **Visitors and pages**: how many requests come in per page, how long they
  take, how many database lookups each one needs, and how often a page
  failed with a server error.
- **The workers**: the programs that serve the pages and send the mail, how
  much memory each one uses, and how much work is waiting for them (see
  :doc:`workers`).
- **The database**: how many connections are open, how many lookups it does
  per second, slow lookups, and the size of every table.
- **The cache** (Redis): how much memory it uses against its limit, and how
  often a page found what it needed in the cache.
- **Mail**: how much mail is waiting, and how long the oldest mail has been
  waiting.

Which of these figures need your attention, and when, is on
:doc:`what-to-watch`.
