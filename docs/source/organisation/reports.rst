Reports
=======

Reports are tables and charts you build yourself on the organisation's
figures: how many children come, per province, per dojo, per age band, how
regularly. Open **Reports** (under **Insights**) in the organisation
dashboard. The **admin** role makes, changes and deletes reports; every
admin can change every report, and the audit log shows who changed what
(see :doc:`audit-log`).

Datasets: figures we prepared
-----------------------------

Every report starts from a **dataset**: figures we prepared for reports,
listed under **Datasets** on the Reports page. You choose what to show,
not where the figures come from. The first dataset is **Children and how
they come**: every child with an engagement stage from last night's
figures (the same stages segments use, see :doc:`segments`), with their
main dojo and its province, age band and gender, whether they're signed up
for a session, and how many sessions they came to and were offered.

A dataset never contains a name, an address or a mail address, nor
anything about health or background checks. It's counts only. **Small
groups are merged**: a group of fewer than five children (say, the girls
aged 7 to 9 at one dojo) gets its most identifying detail replaced by
**Other (small groups)** and is added to the other groups that then match,
starting with the dojo. That way no report can point out a child. Children
who are still in a group that small after that are left out, and the
report says how many; totals are that much lower. With few children, a lot
ends up under **Other**; the more children come, the more detail the
figures keep.

Building a report
-----------------

1. On the Reports page, choose **New report** under a dataset.
2. The settings panel is on the right. Drag columns into **Group by** (the
   rows, for example *Province*) and **Split by** (the columns or the
   colours of a chart, for example *Engagement stage*). Under **Columns**,
   tick what to count, for example *Children*. Drag a column to **Where**
   to show only some of the figures, for example only regular children.
3. At the top left, choose how to show it: a table (**Datagrid**) or a
   chart, such as **Y Bar** for bars.
4. Below, give the report a name, and a description for whoever opens it
   next, and choose **Save**.

Opening a saved report shows it as it was saved, with the figures as of
now (they're updated every hour; the page says when). Change it and choose
**Save**, or **Save as a new report** to keep the original. The settings
button at the top right of the report opens the panel again. **Delete
report** removes the report, never the figures.

A report works in every language: a report saved in Dutch opens in French
with French column names, and the other way round.

Sharing reports with the dojos
------------------------------

Below a report, **Status** decides who sees it besides the admins:

- **Draft**: only the organisation's admins. Work on a report as a draft
  until it's ready.
- **Published**: ready. With **Share with the dojos** ticked, every
  dojo's **champion** also sees it, in their dojo's admin area (see
  :doc:`../dojo-team/reports`). The **Shown to** column on the Reports
  page says who sees each report.

A shared report is read-only for the champions and shows only their own
dojo's figures: each dojo gets its own figures from the site, so a champion
can never see another dojo's. On a dojo's own figures small groups aren't
merged (the dojo's team knows its children from the attendance list), and
the **Main dojo** column and whatever refers to it in the report are left
out. **Order** decides where a report comes on the dojos' Reports page,
lowest first.

Editing a shared report changes it for every dojo at once. To try something
out, use **Save as a new report** and keep the copy as a draft.

Standard reports
----------------

The site comes with a few **standard** reports, published and shared with
every dojo: children per engagement stage, children per age band and
gender, and regular and lapsed children. They show in each reader's
language. You can change them like any report; once you do, the report is
yours and stays as you left it, and it shows the name as you wrote it. A
standard report you haven't touched is brought up to date when the site
gets a new version of it. If you delete one, it comes back with the next
update of the site: to stop sharing it, set it back to **Draft** or untick
**Share with the dojos** instead.

The figures as a file
---------------------

**Download the figures (CSV)** gives a dataset's figures as a spreadsheet
file, with the same merged small groups. It also works without
JavaScript, which building a report needs.
