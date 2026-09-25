Campaigns
=========

A campaign sends one mail to everyone in a segment who wants that kind of
mail: the newsletter, news from their dojo, or volunteering news.

Preparing a campaign
--------------------

Under **Campaigns**, choose **New campaign** and fill in:

- **Name**: for you; people don't see it.
- **Kind of mail**: decides who may get it, based on their mail preferences.
- **Segment**: who it's for (see :doc:`segments`).
- **Template**: the text (see :doc:`mail-templates`). Every person gets it in
  their own language.
- **Template variables**: values the template uses, one per line, like
  ``signup_url: https://...``.
- **Send at**: leave empty to send when you launch it, or pick a time.

The campaign's page shows the mail in every language as it will look, and
how many people it will reach, with examples. **Send a test to me** sends it
to your own address first.

Launching
---------

**Launch** checks the campaign and sends it (or waits until its time). From
that moment the list of people is fixed: changing the segment afterwards
doesn't change who this campaign goes to. The mail goes out gradually, so a
large campaign can take a while. Someone who unsubscribes in the meantime
doesn't get it any more.

While it's going out, **Cancel campaign** stops the mail that hasn't been
sent yet. Once everything is out, the campaign shows as **Sent**, with its
results: how many were sent, held back (unsubscribed, blocked addresses),
bounced or failed, and how many people unsubscribed since.
