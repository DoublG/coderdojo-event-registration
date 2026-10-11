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

The figures as a file
---------------------

**Download the figures (CSV)** gives a dataset's figures as a spreadsheet
file, with the same merged small groups. It also works without
JavaScript, which building a report needs.
