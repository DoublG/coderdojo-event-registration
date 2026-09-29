The organisation dashboard
==========================

The organisation dashboard is where CoderDojo Belgium's own team runs mail to
families and volunteers, chooses which events the public site features, and
handles privacy requests. Everyone with a role in the organisation finds
it under **Manage** in the account menu, and sees the parts their role opens
(see :doc:`people`): the **admin** role everything except background checks,
the **background-check reviewer** role only those (see :doc:`volunteers`),
and the **board** only the page to ask for the Django admin.

If you're also on a dojo's team, the dashboard and your dojos are in the
same place: click **CoderDojo Belgium** at the top of the sidebar to switch
to one of your dojos, and back. The organisation's own events (CoderDojo
Girlz, Coolest Projects, ...) are listed there under **Organisation
events**, and under the same name in the sidebar. They're only there for
people on the **CoderDojo Belgium** dojo's team, which needs a valid
background check (see :doc:`promotions`). Without one you see the
organisation's sections only.

The sidebar has these sections:

- **Campaigns**: one mailing to a group of people, now or at a set time (see
  :doc:`campaigns`).
- **Journeys**: mailings that run by themselves every day, for example to
  families whose child has stopped coming (see :doc:`journeys`).
- **Segments**: who a campaign or journey is for, described with rules
  instead of a list (see :doc:`segments`).
- **Mail templates**: the text of every mail the site sends, in each
  language (see :doc:`mail-templates`).
- **Mail queue**: the mail waiting to go out, failed mail, bounces and
  blocked addresses (see :doc:`mail-queue`).
- **Promotions**: which events are featured where on the public site (see
  :doc:`promotions`).
- **Sponsors**: the sponsors and partners on the homepage (see
  :doc:`sponsors`).
- **Awards**: the badges ninjas can earn at their dojo (see
  :doc:`awards`).
- **Background checks** and **Applications** (under **Volunteers**): the
  criminal-record extracts and applications of new champions and mentors,
  for people with the **background-check reviewer** role only (see
  :doc:`volunteers`).
- **Privacy**: a copy of someone's data, or deleting their account, when
  they ask by mail or post (see :doc:`privacy`).
- **Sign-in security**: which roles must use two-step login (see
  :doc:`sign-in-security`).
- **People** (under **Organisation**): who has which role, giving and
  taking away roles, and inviting someone new (see :doc:`people`).
- **Audit log** (under **Organisation**): who changed what on the site,
  read-only, with sensitive values hidden (see :doc:`audit-log`).
- **Django admin** (under **Organisation**): asking for the site's technical
  admin, for 12 hours, for every role (see :doc:`django-admin`).

People only get mail they want. Every account chooses which kinds of mail
it gets on its **Mail preferences** page; the newsletter and campaigns only
go to people who opted in, and children's own logins never get campaigns.
Addresses that bounced are skipped automatically.

Fixing things by hand when something goes wrong (sending a failed mail
again, unblocking an address, the full mail log) stays in the site's
technical admin, the Django admin. You ask for it when you need it (see
:doc:`django-admin`).

The bell at the top of the dashboard shows notifications for the
organisation, for example when someone opens the Django admin or accepts an
invitation.
