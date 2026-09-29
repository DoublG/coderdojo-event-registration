from lib import BASE, Journey, django, mail_ids, mail_shot, sync_playwright  # noqa: F401

with sync_playwright() as pw:
    j = Journey("champion", pw)
    j.login("owner-51-dojo-westerlo")
    p = j.go("/dojos/51/dashboard/")
    j.shot(
        "dashboard",
        "The dojo dashboard",
        "The champion's home: the next session's attendance, a banner if the dojo isn't active, and the six-month dormancy nudge when the dojo has gone quiet.",
        max_h=1800,
    )
    p = j.go("/dojos/51/manage/")
    j.shot(
        "settings",
        "Dojo settings",
        "At the top, the dojo's status: only the champion launches the dojo, marks it dormant or archives it (never with open sessions) and reopens it. Below, everything on the dojo's public page: name, description in each of the dojo's languages, icon, address (re-geocoded on save), contact details and pathways.",
        max_h=2600,
    )
    p = j.go("/dojos/51/events/")
    j.shot(
        "events",
        "Sessions",
        "All the dojo's sessions with their status (draft, open, closed) and one-click next steps.",
        max_h=1600,
    )
    p = j.go("/dojos/51/events/new/")
    j.shot(
        "new-event",
        "Planning a new session",
        "A new session: date and times (Belgian notation), places, age range, audience (e.g. a girls' session), a banner from the image library or an upload, the team running it and the pathways. It starts as a draft; publishing opens registrations and the families get the new-sessions mail.",
        max_h=2800,
    )
    p = j.go("/dojos/51/events/76/")
    j.shot(
        "event",
        "A full session with a waiting list",
        "The session page shows places taken and the waiting list; when a family cancels, the first child waiting is promoted and their family is mailed.",
        max_h=2200,
    )
    p = j.go("/dojos/51/events/76/attendance/")
    j.shot(
        "attendance",
        "Attendance with health notes",
        "The champion's attendance list also shows the family's allergy and health notes, only for children with a confirmed place, and every view of them is recorded in the audit log.",
        max_h=2000,
    )
    p = j.go("/dojos/51/manage/team/")
    j.shot(
        "team",
        "Managing the team",
        "Accept join requests, add mentors, promote youth mentors, and hand over the champion role to an active mentor.",
        max_h=1800,
    )
    p = j.go("/dojos/51/manage/members/")
    j.shot(
        "members",
        "Members",
        "The children whose home dojo this is, with a button to promote one to youth mentor.",
        max_h=1800,
    )
    p = j.go("/dojos/51/manage/updates/")
    j.shot("updates", "Updates", "Short 'From this dojo' notes shown on the public dojo page.", max_h=1600)
    p = j.go("/dojos/51/manage/mail/")
    j.shot(
        "mail",
        "Mail to the families",
        "The champion writes to the dojo's families (or its own team), at most a few mailings a month. The team sees counts, never families' addresses.",
        max_h=1600,
    )
    p = j.go("/dojos/51/manage/mail/new/")
    j.shot(
        "mail-new",
        "Writing a mailing",
        "Subject and message in each of the dojo's languages and a prepared audience (all families, a child's age or belt, ...). Families reply straight to the dojo's address, and can mute one dojo's news.",
        max_h=2400,
    )
    p = j.go("/dojos/51/manage/api/")
    j.shot(
        "api",
        "API clients",
        "For apps that work for the dojo (e.g. scanning children in at the door): OAuth 2.0 client credentials with attendance scopes, champion only.",
        max_h=1400,
    )
    j.save({"persona": "Champion", "who": "owner-51-dojo-westerlo (champion of Dojo Westerlo)"})
