The workers
===========

The site runs as a handful of programs, called *workers*, that share the
work between them. When the site feels slow, or mail doesn't go out, one of
them is usually the reason.

Web workers: the pages
----------------------

Every page a visitor opens is made by a **web worker**. The site runs
several side by side (four is the plan for the live site), and each one
handles up to 25 visitors at the same moment. That limit is on purpose: every
page being made needs a connection to the database, and the database only
accepts a limited number of them.

When all web workers are full, a new visitor gets a short "busy" answer
straight away, instead of a page that keeps loading. On the development site
that answer is a page in the site's own style, **"One moment"**, which tries
again by itself after 30 seconds; the live server still shows its hosting
provider's plain error page until the provider has set ours up. Getting that
answer now and then during a registration rush (a popular session opening for
sign-up) is normal. Getting it on an ordinary day means the site needs more
web workers.

What the web workers can handle, as measured on a test machine in October
2026: 600 visitors browsing at once, about 110 pages a second, with no errors
and 95 out of 100 pages ready within 0.2 seconds. The live server is slower
than that test machine, so take this as an indication, not a promise.

Background workers: mail and scheduled jobs
-------------------------------------------

Everything that doesn't have to happen while a visitor waits is done by two
**background workers**:

- **The mail worker** sends every mail (booking confirmations, reminders,
  campaigns) and does other work handed to it, one piece at a time. A
  campaign is handed over in small portions, so a booking confirmation never
  waits behind a whole campaign.
- **The scheduler** starts the jobs that run on a clock. Every 10 seconds it
  passes waiting mail on to the mail worker; every few minutes it checks for
  bounced mail and campaigns that are due. Every day it runs:

  ========  ==============================================================================================
  Time      Job
  ========  ==============================================================================================
  02:30     Store the daily sample of the site's size and figures
  03:00     Rebuild how often each child comes to sessions
  09:00     Session reminders; mail reviewers about waiting background checks
  10:00     Delete accounts that haven't been used for two years; clear the text of mail older than a year
  10:30     Remind volunteers whose background check is about to expire
  17:00     Tell families about new sessions at their dojo
  18:00     Send the journeys' mail
  ========  ==============================================================================================

If the background workers stop, the website itself keeps working, but no
mail goes out. Nothing is lost: the mail waits in the queue and goes out as
soon as they run again. The health check and the Mail queue page both say
so when mail has been waiting for more than half an hour.

Memory
------

All workers share the server's memory. Measured under load, the whole site
needs about 1.5 GB at its busiest moment (the web workers about 750 MB, the
background workers about 650 MB during the nightly rebuild at 03:00), so the
plan is an account with 2 GB. How the workers relate to the server's CPU,
memory and disk is on :doc:`server-resources`.
