Audit log
=========

The audit log records who changed what on the site, and who viewed the most
sensitive data: a child's health notes, or a volunteer's background check.
**Audit log** (under **Organisation**) shows it to the organisation's
**admin** role, newest first. It can only be read: nobody can change or
delete an entry, which is what makes it trustworthy.

Each line says when it happened, who did it, what they did (**Created**,
**Changed**, **Deleted** or **Viewed**), which item it was about, and what
changed. **The site itself** means nobody did it by hand: an automatic job,
such as closing a Django admin access after 12 hours.

Hidden values
-------------

Some changes are recorded, but their values are never shown here: health
notes, everything about criminal-record extracts and background checks, and
security data such as passwords, sign-in codes and secret keys. They appear
as ``****``, so you can see *that* they changed and who changed them, but not
what they say.

Finding something
-----------------

Type part of a name, username or email address under **Person or item** to
find the changes to that item, or the changes someone made. **Kind of
change** and **Kind of data** narrow the list further, for example to
everything that was deleted, or to changes to dojos. The log shows 50 lines
per page; use **Older** and **Newer** to go through it.

How long it's kept
------------------

What's in the log about someone is removed with their account, when the
account is deleted after two years without a login or on request (see
:doc:`privacy`). Entries that are no longer about any account are removed
after a while too.
