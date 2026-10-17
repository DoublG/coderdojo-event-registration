Planning your sessions in a spreadsheet
=======================================

Many dojos plan their whole year at once, in Excel. Instead of typing
every session again on the site, a macro in that spreadsheet can put them
on the site for you, through the site's API (see :doc:`api-clients`). Run
it again whenever the plan changes: it updates the same sessions, it never
adds them twice.

Only the dojo's **champion** can set this up, because it needs an API
client.

What you need
-------------

1. On the dojo's **API** page, add a client (for example "Planning
   spreadsheet") and tick only **Plan sessions: add and change them, e.g.
   from a spreadsheet**. Keep the **client ID** and the **client secret**
   it shows.
2. A spreadsheet with a sheet called **Sessions**, laid out as below, and
   a sheet called **Settings** with the client ID in cell **B1**.
3. The macro below, in Excel for Windows (the macro uses a Windows part
   of Excel to reach the site).

The Sessions sheet
------------------

Row 1 holds these headings, exactly as written, one per column from **A**
to **K**. Every row below it is one session.

==============  ==============================================================
Heading         What goes in it
==============  ==============================================================
external_ref    The session's own key: anything that's unique within your
                dojo and **never changes** for that session, for example
                ``2026-W38``. This is how the site recognises the session the
                next time. Change the key and the site sees a new session.
name            The session's name.
date            The day, as a date cell.
start_time      When it starts, as a time cell (14:00).
end_time        When it ends, on the same day.
places          How many children can sign up before new sign-ups go on the
                waiting list; at least 1.
venue_name      Optional. Leave it empty to use the dojo's own address.
min_age         Optional.
max_age         Optional.
audience        Optional: ``everyone`` (when empty) or ``girls``.
status          Optional: ``draft``, ``open`` or ``closed``. A new session
                starts as a draft, hidden from the site, unless you write
                ``open``. Leave it empty to keep the status the session has
                on the site.
==============  ==============================================================

The macro writes the result of each row in columns **L** and **M**.

What a run does
---------------

For every row, column **L** says what happened, and **M** why:

- **created**: a new session, as a draft unless its status says otherwise.
- **updated**: the session changed to match the row.
- **unchanged**: the session already matched the row.
- **skipped**: the session has already started, so the spreadsheet leaves
  it alone. Change it on the site if you need to.
- **error**: this row wasn't saved, for example because the end time is
  before the start time, the day is in the past, or the same key is on
  two rows. The other rows are saved anyway: fix this one and run the
  macro again.

Send every column on every run: an empty venue or age in the spreadsheet
also empties it on the site.

**A run never deletes a session.** Taking a row out of the spreadsheet
changes nothing on the site. To stop a planned session, set its status to
``draft`` (hidden) or ``closed``; to delete it, use the session's page on
the site.

The description, the picture, the team and the pathways aren't in the
spreadsheet: set them on the session's page on the site, and the next run
keeps them. A new session gets the pathways your dojo provides, as it
does on the site.

The macro
---------

In Excel, open **Developer** → **Visual Basic** (or press Alt+F11),
choose **Insert** → **Module**, and paste the code below. Put your site's
address in the first line (it's at the bottom of the **API** page) and
save the file as an **Excel Macro-Enabled Workbook** (``.xlsm``). The
macro sends rows 2 to the last filled row of column **A**, so keep the
sessions together, without empty rows in between. Run it
with **Developer** → **Macros** → **SyncSessions**. It asks for the client
secret every time, so the secret is never saved in the file.

.. code-block:: vbscript

   Const SITE As String = "https://..."   ' the site's address, without a / at the end

   Sub SyncSessions()
       Dim ws As Worksheet, http As Object, re As Object, found As Object
       Dim clientId As String, secret As String, token As String, body As String
       Dim r As Long, c As Long, lastRow As Long, i As Long

       Set ws = ThisWorkbook.Worksheets("Sessions")
       clientId = ThisWorkbook.Worksheets("Settings").Range("B1").Value
       secret = InputBox("Client secret")
       If secret = "" Then Exit Sub

       ' 1. A token, with the client ID and secret.
       Set http = CreateObject("WinHttp.WinHttpRequest.5.1")
       http.Open "POST", SITE & "/api/oauth/token/", False
       http.SetRequestHeader "Content-Type", "application/x-www-form-urlencoded"
       http.Send "grant_type=client_credentials&client_id=" & clientId & "&client_secret=" & secret
       If http.Status <> 200 Then MsgBox "No token: " & http.ResponseText: Exit Sub
       Set re = CreateObject("VBScript.RegExp")
       re.Pattern = """access_token"":\s*""([^""]+)"""
       token = re.Execute(http.ResponseText)(0).SubMatches(0)

       ' 2. Every row as JSON (at most 200 rows per run).
       lastRow = ws.Cells(ws.Rows.Count, 1).End(xlUp).Row
       body = "{""events"": ["
       For r = 2 To lastRow
           If r > 2 Then body = body & ","
           body = body & "{"
           For c = 1 To 11
               If c > 1 Then body = body & ","
               body = body & """" & ws.Cells(1, c).Value & """: " & JsonValue(ws.Cells(r, c).Value)
           Next c
           body = body & "}"
       Next r
       body = body & "]}"

       ' 3. Send them, and write each row's result next to it.
       http.Open "POST", SITE & "/api/v1/events/sync", False
       http.SetRequestHeader "Authorization", "Bearer " & token
       http.SetRequestHeader "Content-Type", "application/json"
       http.Send body
       If http.Status <> 200 Then MsgBox "Not synced: " & http.ResponseText: Exit Sub
       re.Global = True
       re.Pattern = """outcome"":\s*""(\w+)""[^}]*?""detail"":\s*""((?:[^""\\]|\\.)*)"""
       Set found = re.Execute(http.ResponseText)
       ws.Range("L1:M1").Value = Array("result", "detail")
       For i = 0 To found.Count - 1
           ws.Cells(i + 2, 12).Value = found(i).SubMatches(0)
           ws.Cells(i + 2, 13).Value = found(i).SubMatches(1)
       Next i
       MsgBox "Done: see columns L and M."
   End Sub

   Function JsonValue(v As Variant) As String
       If IsEmpty(v) Then
           JsonValue = "null"
       ElseIf VarType(v) = vbDate Then
           If Int(CDbl(v)) = 0 Then
               JsonValue = """" & Format(v, "hh:nn") & """"
           Else
               JsonValue = """" & Format(v, "yyyy-mm-dd") & """"
           End If
       ElseIf VarType(v) = vbString Then
           JsonValue = """" & Replace(Replace(v, "\", "\\"), """", "\""") & """"
       Else
           JsonValue = Replace(CStr(v), ",", ".")
       End If
   End Function

Keep the secret safe
--------------------

Anyone with the client ID and secret can change your dojo's sessions. Give
this client only **Plan sessions**, so it can't see who signed up or who
came. If the secret may have leaked, give the client a **New secret** on
the **API** page: the old one stops working at once.

For other tools
---------------

Any tool or language can do the same: ask for a token, then send the rows
to ``/api/v1/events/sync``. The **Reference** link on the **API** page
describes every field.
