Apps that work for your dojo (API)
===================================

An app or website can work for your dojo through the site's API: an app
at the door that marks which children and team members came, so you
don't have to tick them off on the attendance list, or a spreadsheet that
puts the sessions you planned on the site (see
:doc:`planning-sessions`). Only the dojo's **champion** can let
an app in.

Adding a client
---------------

In the sidebar, under **Dojo**, open **API** (only the champion sees it).
Under **Add a client**, give it a name you'll recognise (for example
"Scan app at the door") and choose what it may do:

- **See the sessions and who has a place**: your dojo's sessions, and for
  each one the children with a confirmed place (with the family's answers
  to the session's sign-up questions) and the session's team.
- **Mark who came**: mark a child or team member present, absent or not
  marked yet, or everyone present at once, and correct a child's answer to
  a sign-up question.
- **See the sessions**: your dojo's sessions only, without who signed up.
- **Plan sessions: add and change them, e.g. from a spreadsheet**: add
  sessions and change them (name, day and times, places, venue, ages,
  status). It never deletes a session.

Tick only what the app needs: a planning spreadsheet needs only **Plan
sessions**, an app at the door only the first two.

After **Add client**, the page shows the client's **client ID** and
**client secret**. Give both to whoever sets up the app. **The secret is
shown only this once**: we only keep a scrambled copy, so we can't show it
again. If it gets lost, make a new one (below).

What an app can and can't do
----------------------------

A client only ever works for your dojo, and only does what you allowed.
It never sees children's allergies or notes, their family, or anything
else from their account. What it marks or changes is recorded under the
client's own name, not yours.

New secret and deleting
-----------------------

In **Your clients**:

- **New secret** gives the client a new secret; the old one stops working
  at once. Use it when the secret may have leaked, or got lost.
- **Delete** stops the client at once and removes it from the list. What
  it marked stays.

The list also shows when each client was last used.

For the app's developer
-----------------------

The bottom of the **API** page has the addresses the app needs. The app
asks for a token with its client ID and secret (OAuth 2.0, client
credentials), which lasts an hour, and sends it with every request. The
**Reference** link is the full, technical description of the API.
