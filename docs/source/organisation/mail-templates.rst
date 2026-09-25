Mail templates
==============

Every mail the site sends has a template: its subject and text, in each
language. Under **Mail templates** you see them all, the languages each one
exists in, and what uses it: the site itself (booking confirmations,
reminders, password resets, and so on) or campaigns and journeys.

Editing
-------

Open a template and pick a language tab. Change the subject and text and
**Save**. The preview on the right shows the mail with example data.

Parts between ``{{`` and ``}}`` are filled in for each person, for example
``{{ recipient_name }}``; the page lists the ones this template can use.
Dates take a format, like ``{{ start_time|date:"l j F" }}``, and day and
month names follow the mail's language. A template that doesn't work is
refused with an explanation, so a broken mail never goes out.

A language that has no version of its own uses the English one. Opening
that language's tab starts from the English text, ready to translate.

New templates and deleting
--------------------------

**New template** creates one for campaigns and journeys; write the English
version first. You can delete a language version (English then takes its
place) or a whole campaign template. The site's own templates and the
English version of any template can't be deleted, and neither can a
template a campaign that hasn't gone out yet still uses.
