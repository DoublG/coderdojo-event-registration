Segments: who gets a mail
=========================

A segment describes a group of people with rules, for example "parents of a
girl aged 9 to 14 who lives within 25 km of Ghent". It's worked out again
every time it's used, so it's always up to date.

Building a segment
------------------

Under **Segments**, choose **New segment** and give it a name. Then add
groups of rules:

- A group about **Accounts** tests the account itself: its role (parent,
  mentor, champion), its language, where the family lives (province, or a
  distance from a dojo), when it was created.
- A group about **Parents of a child who…** tests the children. All rules in
  such a group are about *the same child*: "a girl" and "aged 9 to 14" means
  one child who is both. The mail goes to that child's parents.

Each group matches when **all** or **any** of its rules match, as you
choose. Groups at the top level must all match. Groups can hold nested
groups, e.g. accounts that are mentors, or parents of a child who came to a
session recently.

To add a rule, pick what it's about; the fields that fit appear next to it
(a list to tick, a number of days, a dojo and a distance). Each rule is then
shown as a sentence. The right-hand side shows how many accounts match, with
some examples.

How a child comes to sessions
-----------------------------

Several rules use the figures the site works out every night from the
attendance dojos mark: whether a child is **new**, **regular**,
**occasional**, **at risk** (missed the last three sessions meant for
them), **lapsed** (not in the last six months), **never came** or **aged
out**, how many sessions they came to, how many they missed in a row, and
when this changed. Only sessions meant for the child count: their age range,
and girls' sessions only for girls.

A segment only says who *could* get a mail. A campaign or journey sends it
only to those who want that kind of mail.
