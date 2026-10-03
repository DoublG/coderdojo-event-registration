CPU, memory and disk
====================

Three things limit what the server can do: its **CPU** (how much work it can
do per second), its **memory** (how many workers fit at once) and its **disk**
(how much it can keep). Every worker uses some of each. This page explains how
the workers (see :doc:`workers`) relate to them, so you know which of the three
to look at, and what to change when one runs short.

At a glance
-----------

.. list-table::
   :header-rows: 1
   :widths: 12 30 24 34

   * - Resource
     - What uses it
     - Where to see it
     - When to act
   * - CPU
     - The web workers, making pages; the nightly rebuild at 03:00
     - The hosting provider's control panel (the site's own dashboard doesn't
       measure it)
     - Busy above 80% for ten minutes outside a registration rush, or pages
       getting slower while memory is fine
   * - Memory
     - Every worker holds its own copy of the site; the background workers
       most during the nightly rebuild
     - The dashboard (*PSS per role*), and the hosting provider's panel
     - All workers together above 80% of the server's memory
   * - Disk
     - The database (mostly the mail log), uploaded images, logs and backups
     - *Largest tables* on the dashboard and the daily sample; the hosting
       provider's panel for the whole disk
     - Growing faster than planned, or more than 80% full

CPU: cores, workers and threads
-------------------------------

A server's CPU has a number of **cores**, and each core does one thing at a
time. A **worker** is one program, and the site's code (Python) runs a
worker's work on one core at a time. So each worker can keep at most one core
busy, and four web workers can use at most four cores at once.

Inside each web worker are **threads**: a couple of dozen of them. They don't
let a worker compute more at once; they let it *wait* for many things at once:
the database's answer, a visitor on a slow connection. Waiting costs no CPU.
That's why one web worker can take 25 visitors at the same moment, while it
only works on one of them at any instant.

What a page costs, measured on a test machine in October 2026: about 27
thousandths of a second (ms) of CPU in the web worker, and about 2 ms in the
database. So one core makes about 35 pages a second, and 57 pages a second kept
1.6 cores busy. The live server's cores are slower, so expect fewer pages per
core there; the ratio between the workers and the database carries over.

What follows from that:

- **No more web workers than cores.** A worker more than the server has cores
  doesn't make pages faster: the workers take turns on the same cores, and
  the extra one only uses memory. Leave some room for the database and the
  background workers if they run on the same server.
- **The background workers use at most one core each**, since each does one
  job at a time. Sending mail barely uses CPU; the nightly rebuild at 03:00
  keeps one core busy while it runs.
- **The database uses little CPU** for the site's pages: about a tenth of what
  the web workers use.
- **Slow pages with idle CPU** are not a CPU problem: then the workers are
  waiting, on the database or on a full set of 25 visitors each (see
  :doc:`what-to-watch`).

Memory: one copy of the site per worker
---------------------------------------

Every worker loads the whole site into memory, so memory grows with the number
of workers, not with the number of visitors. Measured under load: the four web
workers together about 750 MB (each extra web worker adds about 100 to 200 MB),
the background workers up to about 650 MB during the nightly rebuild, and the
cache under 50 MB. The whole site needs about 1.5 GB at its busiest moment, so
the plan is a server with 2 GB. The database comes on top of that if it runs on
the same server.

When memory runs out, the server stops a worker abruptly. So the number of web
workers is limited by both: the cores (for speed) and the memory (for room).
Add cores and memory together.

Disk: what grows
----------------

The disk is about space, not speed: the site reads little from it, since what
it reads often is in memory or in the cache.

- **The database** grows by about 350 MB a year at 100 dojos and 6,000
  families, two thirds of it the mail log. A mail's text is cleared a year
  after it was sent, which keeps that growth in check.
- **Uploaded images** (event banners, dojo logos, photos): at most 10 MB each,
  and made smaller when they're stored.
- **Logs and backups**: these depend on how the hosting provider keeps them.

The dashboard shows each table's size now; the daily sample (every night at
02:30) stores the database's size in the site itself, so its growth over months
can be followed even without a monitoring service.
