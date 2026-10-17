Planning sessions with your own tools
=====================================

Many dojos plan their whole year at once, for example in a spreadsheet.
Instead of typing every session again on the site, your own tool can put
them on the site through the site's API (see :doc:`api-clients`): a
spreadsheet macro, a script, or anything else that can send a request to
a website. Which tool you use, and how you build it, is up to you; the
examples at the end of this page can get you started. Send the plan
again whenever it changes: the site updates the same sessions, it never
adds them twice.

Only the dojo's **champion** can set this up, because it needs an API
client.

Getting started
---------------

On the dojo's **API** page, add a client (for example "Planning
spreadsheet") and tick only **Plan sessions: add and change them, e.g.
from a spreadsheet**. Give its **client ID** and **client secret** to
whoever builds the tool. The bottom of the **API** page has the addresses
it needs, and the **Reference** link describes every field exactly.

The tool sends your sessions to ``/api/v1/events/sync``, at most 200 per
call. Tools that run in a browser, such as Excel on the web, can call the
API too.

What to send for each session
-----------------------------

==============  ==============================================================
Field           What goes in it
==============  ==============================================================
external_ref    The session's own key: anything that's unique within your
                dojo and **never changes** for that session, for example
                ``2026-W38``. This is how the site recognises the session the
                next time. Change the key and the site sees a new session.
name            The session's name.
date            The day.
start_time      When it starts (14:00).
end_time        When it ends, on the same day.
places          How many children can sign up before new sign-ups go on the
                waiting list; at least 1.
venue_name      Optional. Leave it empty to use the dojo's own address.
min_age         Optional.
max_age         Optional.
audience        Optional: ``everyone`` (when empty) or ``girls``.
status          Optional: ``draft``, ``open`` or ``closed``. A new session
                starts as a draft, hidden from the site, unless you send
                ``open``. Leave it empty to keep the status the session has
                on the site.
==============  ==============================================================

Send every field every time: an empty venue or age also empties it on the
site.

What the site answers
---------------------

For every session it says what happened, and why:

- **created**: a new session, as a draft unless its status says otherwise.
- **updated**: the session changed to match.
- **unchanged**: the session already matched.
- **skipped**: the session has already started, so the site leaves it
  alone. Change it on the site if you need to.
- **error**: this session wasn't saved, for example because the end time
  is before the start time, the day is in the past, or the same key was
  sent twice. The others are saved anyway: fix this one and send it again.

**Sending never deletes a session.** Leaving a session out changes nothing
on the site. To stop a planned session, set its status to ``draft``
(hidden) or ``closed``; to delete it, use the session's page on the site.

The description, the picture, the team and the pathways aren't sent: set
them on the session's page on the site, and the next sync keeps them. A
new session gets the pathways your dojo provides, as it does on the site.

Examples: a macro for Excel or LibreOffice
------------------------------------------

The two macros below are **only examples**, to show how it can work. They
aren't part of the site and we don't keep them working for every version
of Excel or LibreOffice: copy one, adapt it to your own spreadsheet, and
test it on a few sessions first.

Both expect the same spreadsheet:

- a sheet called **Sessions**, with the field names above as headings in
  row 1, from **A** (``external_ref``) to **K** (``status``), and one
  session per row below it, without empty rows in between. Dates and
  times can be ordinary date and time cells.
- a sheet called **Settings**, with the client ID in cell **B1**.

They ask for the client secret on every run, so the secret is never saved
in the file, and write the site's answer for each row in columns **L**
(what happened) and **M** (why). Put your site's address in the line that
starts with ``SITE`` (it's at the bottom of the **API** page).

Excel for Windows
~~~~~~~~~~~~~~~~~

This one uses a Windows part of Excel to reach the site, so it doesn't
run in Excel for Mac or Excel on the web. In Excel, open **Developer** →
**Visual Basic** (or press Alt+F11), choose **Insert** → **Module**, paste
the code and save the file as an **Excel Macro-Enabled Workbook**
(``.xlsm``). Run it with **Developer** → **Macros** → **SyncSessions**.

.. code-block:: vbscript

   ' An example only: adapt it to your own spreadsheet.
   Const SITE As String = "https://..."   ' the site's address, without a / at the end
   Const LANGUAGE As String = "en"        ' the language of the answers: en, nl or fr

   Sub SyncSessions()
       Dim ws As Worksheet, http As Object
       Dim clientId As String, secret As String, token As String, body As String, answer As String
       Dim r As Long, c As Long, lastRow As Long, pos As Long, outcome As String

       Set ws = ThisWorkbook.Worksheets("Sessions")
       clientId = ThisWorkbook.Worksheets("Settings").Range("B1").Value
       secret = InputBox("Client secret")
       If secret = "" Then Exit Sub

       ' 1. A token, with the client ID and secret.
       Set http = CreateObject("WinHttp.WinHttpRequest.5.1")
       http.Open "POST", SITE & "/api/oauth/token/", False
       http.SetRequestHeader "Content-Type", "application/x-www-form-urlencoded"
       http.Send "grant_type=client_credentials" _
           & "&client_id=" & WorksheetFunction.EncodeURL(clientId) _
           & "&client_secret=" & WorksheetFunction.EncodeURL(secret)
       If http.Status <> 200 Then MsgBox "No token: " & http.ResponseText: Exit Sub
       pos = 1
       token = JsonText(http.ResponseText, "access_token", pos)

       ' 2. Every row as JSON. Dates and times go as Excel's own numbers,
       '    which the site understands.
       lastRow = ws.Cells(ws.Rows.Count, 1).End(xlUp).Row
       body = "{""events"": ["
       For r = 2 To lastRow
           If r > 2 Then body = body & ","
           body = body & "{"
           For c = 1 To 11
               If c > 1 Then body = body & ","
               body = body & """" & ws.Cells(1, c).Value & """: " & JsonValue(ws.Cells(r, c).Value2)
           Next c
           body = body & "}"
       Next r
       body = body & "]}"

       ' 3. Send them, and write each row's answer next to it.
       http.Open "POST", SITE & "/api/v1/events/sync", False
       http.SetRequestHeader "Authorization", "Bearer " & token
       http.SetRequestHeader "Content-Type", "application/json"
       http.SetRequestHeader "Accept-Language", LANGUAGE
       http.Send body
       If http.Status <> 200 Then MsgBox "Not synced: " & http.ResponseText: Exit Sub
       answer = http.ResponseText
       ws.Range("L1:M1").Value = Array("result", "detail")
       ws.Range("L2:M" & ws.Rows.Count).ClearContents
       pos = 1
       r = 2
       Do
           outcome = JsonText(answer, "outcome", pos)
           If pos = 0 Then Exit Do
           ws.Cells(r, 12).Value = outcome
           ws.Cells(r, 13).Value = JsonText(answer, "detail", pos)
           r = r + 1
       Loop
       MsgBox "Done: see columns L and M."
   End Sub

   ' A cell's value as JSON.
   Function JsonValue(v As Variant) As String
       Dim s As String
       If IsEmpty(v) Then
           s = "null"
       ElseIf VarType(v) = vbString Then
           s = Replace(Replace(v, "\", "\\"), """", "\""")
           s = """" & Replace(Replace(s, vbCr, ""), vbLf, "\n") & """"
       Else
           s = Trim(Str(v))   ' Str always writes a decimal point, never a comma
           If Left(s, 1) = "." Then s = "0" & s
       End If
       JsonValue = s
   End Function

   ' The text of the next "key" in json, from position pos on. Moves pos
   ' past it, or sets it to 0 when there's no more.
   Function JsonText(json As String, key As String, pos As Long) As String
       Dim ch As String, s As String
       If pos < 1 Then Exit Function
       pos = InStr(pos, json, """" & key & """")
       If pos = 0 Then Exit Function
       pos = InStr(pos + Len(key) + 2, json, ":") + 1
       Do While Mid(json, pos, 1) = " ": pos = pos + 1: Loop
       If Mid(json, pos, 1) <> """" Then Exit Function   ' null or a number
       pos = pos + 1
       Do
           ch = Mid(json, pos, 1)
           If ch = "" Or ch = """" Then Exit Do
           If ch = "\" Then
               pos = pos + 1
               ch = Mid(json, pos, 1)
               If ch = "u" Then
                   ch = ChrW(CLng("&H" & Mid(json, pos + 1, 4)))
                   pos = pos + 4
               ElseIf ch = "n" Then
                   ch = vbLf
               End If
           End If
           s = s & ch
           pos = pos + 1
       Loop
       JsonText = s
   End Function

LibreOffice Calc
~~~~~~~~~~~~~~~~

This one is a Python macro, so it runs in LibreOffice 7.2 or later on
Windows, macOS and Linux (on Linux, you may need to install LibreOffice's
Python support, often a package called
``libreoffice-script-provider-python``). Save the code as
``sync_sessions.py`` in the ``Scripts/python`` folder of your LibreOffice
profile (make the folders if they aren't there yet):

- Windows: ``%APPDATA%\LibreOffice\4\user\Scripts\python``
- macOS: ``~/Library/Application Support/LibreOffice/4/user/Scripts/python``
- Linux: ``~/.config/libreoffice/4/user/Scripts/python``

Then open your spreadsheet and run it with **Tools** → **Macros** →
**Run Macro…** → **My Macros** → **sync_sessions** → **sync_sessions**.

.. code-block:: python

   # An example only: adapt it to your own spreadsheet.
   import json
   import urllib.error
   import urllib.parse
   import urllib.request

   from com.sun.star.sheet.CellFlags import STRING, VALUE
   from scriptforge import CreateScriptService

   SITE = "https://..."  # the site's address, without a / at the end
   LANGUAGE = "en"  # the language of the answers: en, nl or fr


   def post(url, data, headers):
       request = urllib.request.Request(url, data=data, headers=headers, method="POST")
       with urllib.request.urlopen(request, timeout=60) as response:
           return json.load(response)


   def sync_sessions(*args):
       basic = CreateScriptService("Basic")
       sheets = XSCRIPTCONTEXT.getDocument().Sheets
       sessions = sheets.getByName("Sessions")
       client_id = sheets.getByName("Settings").getCellRangeByName("B1").getString()
       secret = basic.InputBox("Client secret")
       if not secret:
           return

       try:
           # 1. A token, with the client ID and secret.
           form = {"grant_type": "client_credentials", "client_id": client_id, "client_secret": secret}
           token = post(
               SITE + "/api/oauth/token/",
               urllib.parse.urlencode(form).encode(),
               {"Content-Type": "application/x-www-form-urlencoded"},
           )["access_token"]

           # 2. Every row up to the first empty one in column A. Dates and
           #    times go as the spreadsheet's own numbers, which the site
           #    understands.
           cursor = sessions.createCursor()
           cursor.gotoEndOfUsedArea(False)
           rows = sessions.getCellRangeByPosition(0, 0, 10, cursor.RangeAddress.EndRow).getDataArray()
           headings, events = rows[0], []
           for row in rows[1:]:
               if row[0] == "":
                   break
               events.append(dict(zip(headings, row)))

           # 3. Send them, and write each row's answer next to it.
           answer = post(
               SITE + "/api/v1/events/sync",
               json.dumps({"events": events}).encode(),
               {
                   "Authorization": "Bearer " + token,
                   "Content-Type": "application/json",
                   "Accept-Language": LANGUAGE,
               },
           )
       except urllib.error.HTTPError as error:
           basic.MsgBox("Not synced: " + error.read().decode())
           return
       except urllib.error.URLError as error:
           basic.MsgBox("The site can't be reached: " + str(error.reason))
           return

       sessions.getCellRangeByPosition(11, 1, 12, sessions.Rows.Count - 1).clearContents(STRING | VALUE)
       results = (("result", "detail"),) + tuple((row["outcome"], row["detail"]) for row in answer["results"])
       sessions.getCellRangeByPosition(11, 0, 12, len(results) - 1).setDataArray(results)
       basic.MsgBox("Done: see columns L and M.")


   g_exportedScripts = (sync_sessions,)

Keep the secret safe
--------------------

Anyone with the client ID and secret can change your dojo's sessions.
Don't save the secret in a file you share, and give this client only
**Plan sessions**, so it can't see who signed up or who came. If the
secret may have leaked, give the client a **New secret** on the **API**
page: the old one stops working at once.
