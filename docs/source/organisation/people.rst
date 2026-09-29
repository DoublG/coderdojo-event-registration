People and roles
================

The **People** page on the organisation dashboard lists everyone with a
role in the organisation, and is where the organisation's admins give and
take away those roles. Only people with the **admin** role see it.

The roles
---------

The roles are fixed. **What each role opens** on the People page shows what
each one gives:

- **Admin**: the whole organisation dashboard (campaigns, journeys,
  segments, mail templates, the mail queue, promotions, sponsors, awards,
  privacy, sign-in security, these People pages and the audit log).
- **Background-check reviewer**: background checks and applications (see
  :doc:`volunteers`). Reviewers read criminal-record extracts, so only give
  this role to the people who need it.
- **Board**: read-only oversight, in the Django admin.

Someone can have several roles. Every role can also ask for the Django admin
for 12 hours when it's needed (see :doc:`django-admin`).

Giving someone a role
---------------------

Choose **Add a person** and search for their account by name, email address
or username. On their page, tick their roles and choose **Save roles**. They
get a mail saying which roles they now have and where to find the
dashboard. Taking roles away works the same way: untick them and save. Their
account itself stays as it was.

A few rules keep this safe:

- You can't change your own roles: ask another admin.
- The organisation always keeps at least one admin, so the last admin's
  role can't be taken away.
- Only an adult's account can have a role, never a child's own login.

Someone's page also shows every change to their roles (who made it, and
when) and each time they had the Django admin, with their reason.

Inviting someone without an account
-----------------------------------

When the person has no account yet, fill in **Invite someone without an
account** on the **Add a person** page: their name, their email address,
the language of the invitation and their roles. They get a mail with a link
that works for 14 days. With it, they create their own account, with a
password or a login link (or log in, if they made one since), and accept. The roles only go to an account with
the email address you invited, so a forwarded link gives nobody anything.

Invitations that haven't been accepted yet are listed on the People page,
with **Send again** (a new link; the old one stops working) and
**Withdraw**. You get a notification when someone accepts.

Open access and superusers
--------------------------

The People page also lists who has the Django admin open right now, with
their reason and until when. **End now** closes it straight away.

Superusers are listed there too, read-only. They're made on the server by
the site's technical team, never on this page.
