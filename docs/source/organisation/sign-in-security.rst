Sign-in security
================

Anyone can turn on two-step login for their own account (see
:doc:`../families/two-step-login`). On the organisation dashboard's
**Sign-in security** page you decide which roles **must** use it.

Minimum sign-in per role
------------------------

For each role, choose the minimum:

- **Password or login link (two-step login optional)**, the default.
  Whether someone logs in with a password or with a login link is their
  own choice (see :doc:`../families/logging-in-with-a-link`); the levels
  below come on top of either.
- **Two-step login (authenticator app or passkey)**.
- **Two-step login with a passkey**: the strongest, since a passkey can't
  be tricked by a fake site.

The roles are superusers, the organisation's admins, board members,
background-check reviewers, champions, mentors and every adult account
(parents too). An account with several roles gets the strongest level.
Children's own logins can use two-step login too, but are never asked.

With **Required from** you give people time: until that day they see a
notice at the top of every page, with a link to set it up. From that day on
(or right away, when you leave it empty), an account without the right
second step is sent to set it up before it can use anything its role opens:
the dojo's dashboard, this organisation dashboard, or the Django admin.
Someone who is already logged in without their second step is asked to log
in again.

The table shows, per role, how many accounts there are, how many already
use two-step login, how many have a passkey and how many log in with a
login link, so you can see who still
has to set it up before you make it required. The **People** page marks each
person whose role asks for two-step login they haven't set up yet (see
:doc:`people`).

Someone can't log in
--------------------

When someone lost their phone or passkey **and** their backup codes, first
check it's really them, for example by calling them. Then search for their
account under **Someone can't log in** and choose **Turn off two-step
login**. They get a mail and log in without the second step. If their role
needs two-step login, they're asked to set it up again straight away.

You can't do this for your own account: change your own sign-in methods on
your account's Sign-in security page.
