What to watch for
=================

Most figures move up and down with the number of visitors, and that's fine.
The ones below are the warning signs: each one with when it needs attention
and what is most likely behind it. Ask whoever runs the server to act on
them.

Is the site up?
---------------

- **The health check isn't ok.** It names the part that isn't working: the
  database, the cache, or the mail workers. Restarting that part is the
  first step.
- **Server errors** (on the dashboard: *5xx/s*). Should be zero. A few in a
  row on one page usually mean a bug on that page; many on every page mean
  the database or the cache is down.

Is it fast enough?
------------------

- **Response time**: the dashboard shows how long the slowest 5 in 100 pages
  take (*p95*). Under 0.5 seconds is good. Over 1 second for ten minutes or
  more means there are too few web workers for the visitors.
- **"Busy" answers outside a registration rush**: the web workers
  are full on an ordinary day; the site needs more of them (see
  :doc:`workers`).
- **Database lookups per page**: stays about the same however busy the site
  is (5 to 7 for most pages). If it climbs after an update, a page has
  started doing far more work than it should: tell the developers.
- **Cache hit ratio**: the share of reads that found their data in the cache.
  It should stay above 90%. Lower means something is clearing the cache
  over and over, and every page then does the slow work again.

Is there room enough?
---------------------

- **Database connections** over 70% of the limit: more web workers than the
  database can take. Every page being made holds one connection, so the
  number of workers times 25 has to stay below the database's limit.
- **Memory**: the memory of all workers together over 80% of what the
  server has. Running out can make the server stop workers abruptly.
- **Cache memory** over half of its limit (128 MB), or keys being thrown out
  (*evicted*): the cache is too small.
- **Database size** growing faster than planned (the daily sample): usually
  more mail than expected. The text of a mail is kept for a year, so a busy
  year of campaigns shows up here before the nightly clean-up catches up.
- **Uploaded files** growing by more than 100 MB a month: unusually large
  uploads.

Is the mail going out?
----------------------

- **Oldest mail waiting** for more than 30 minutes: the background workers
  have stopped. Restart them; the waiting mail then goes out by itself.
- **Waiting tasks** (*Celery queue length*) above 500 for half an hour:
  the mail worker is stuck or far too slow. Right after a campaign is
  launched, a long queue is normal and shrinks within minutes.
- **Failed mail and bounces** on the Mail queue page: a sudden rise usually
  means a problem with the mail server rather than with the addresses.
