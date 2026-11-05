from lib import BASE, Journey, django, keep_upcoming, laptop_question, mail_ids, mail_shot, sync_playwright  # noqa: F401

with sync_playwright() as pw:
    laptop_question(76, 77, answer_places=True)
    keep_upcoming(77)
    # A clean slate for the session notices (§31): at most three a day per session.
    django("from events.models import SessionNotice; SessionNotice.objects.filter(event_id=77).delete()")
    # The family whose mail is shown: one with the PDF's language as its mail language.
    family = (
        "guardian-1@coderdojo-demo.example" if __import__("lib").LANG == "nl" else "guardian-2@coderdojo-demo.example"
    )
    before = mail_ids(family)
    j = Journey("champion", pw)
    j.login("owner-51-dojo-westerlo")
    p = j.go("/dojos/51/dashboard/")
    j.shot(
        "dashboard",
        "The dojo dashboard",
        "The champion's home: what needs attention (join requests, unmarked attendance, drafts or sessions without a team, the team's background checks running out), the next session with its places and sign-up answers, the coming sessions as an agenda, the ninjas as counts per stage and the year's figures.",
        max_h=1800,
    )
    p = j.go("/dojos/51/manage/")
    j.shot(
        "settings",
        "Dojo settings",
        "At the top, the dojo's status: only the champion launches the dojo, marks it dormant or archives it (never with open sessions) and reopens it. Below, everything on the dojo's public page: name, description in each of the dojo's languages, icon, address (re-geocoded on save), contact details and pathways.",
        max_h=2600,
    )
    j.shot(
        "default-questions",
        "Default sign-up questions",
        "Below the profile, the dojo's default sign-up questions: yes/no questions every new session starts with (here the laptop question), in each of the dojo's languages. Each session can change them on its own page.",
        selector="#default-questions",
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
        "A new session: date and times (Belgian notation), places, age range, audience (e.g. a girls' session), a banner from the image library or an upload, the team running it and the pathways. It starts with the dojo's default sign-up questions, and as a draft; publishing opens registrations and the families get the new-sessions mail.",
        max_h=2800,
    )
    p = j.go("/dojos/51/events/77/")
    j.shot(
        "event",
        "A full session with a waiting list",
        "The session page shows places taken and the waiting list; when a family cancels, or the team adds places, the first children waiting are promoted and their families are mailed. Its Sign-up questions card asks families yes/no questions per child (here the laptop question), with the totals for confirmed places and the waiting list. Mail the families is for telling them about a change; after a save that changes the venue, the times or the places, it offers the matching prepared mail.",
        max_h=2200,
    )
    p.on("dialog", lambda d: d.accept())  # Send asks "Send this mail to the families now?"
    p = j.go("/dojos/51/events/77/notify/?kind=message")
    p.fill("#id_subject", "Ingang via de achterkant")
    p.fill(
        "#id_message",
        "Hallo! Zaterdag is de voordeur dicht door werken. Kom binnen via de ingang aan de parking achteraan, we hangen pijlen op. Tot dan!",
    )
    if p.locator("[name='tr__en-us__subject']").count():
        p.locator("details:has([name='tr__en-us__subject'])").evaluate("d => (d.open = true)")
        p.fill("[name='tr__en-us__subject']", "Entrance at the back")
        p.fill(
            "[name='tr__en-us__message']",
            "Hi! On Saturday the front door is closed for building work. Come in through the entrance by the car park at the back, we'll put up arrows. See you then!",
        )
    p.click("button[name=preview]")
    p.wait_for_load_state("networkidle")
    j.shot(
        "notify",
        "Telling the families about a change",
        "A prepared mail about a new venue, new times or the number of places (with the values from before, so the mail says what changed), or a message of the team's own, to the families with a place, on the waiting list or both, with a count for each. Preview shows the mail as the first family gets it; every family gets it in its own language, with the team's text in that language when they wrote one.",
        max_h=2400,
    )
    p.click("button[name=send]")
    p.wait_for_load_state("networkidle")
    j.shot(
        "notified",
        "Sent",
        "The mail goes to the parents and guardians of every child in the group (and a child's own login with an address), one mail per family. The session's page lists what was sent, when, to how many accounts and by whom. Families can't switch these mails off, so a session gets at most three a day.",
        max_h=1600,
    )
    mail_shot(
        j,
        family,
        before,
        "notice-mail",
        "The mail the families get",
        "In the family's own mail language, with the session's details and the team's text. Replies go to the dojo's address.",
    )
    p = j.go("/dojos/51/events/77/cancel/")
    j.shot(
        "cancel",
        "Calling a session off",
        "Cancel session… asks first. A cancelled session stays on its page, marked as cancelled, so families who look it up see what happened; nobody can sign up, it drops out of the session lists and reminders, and the registrations are kept. Ticked, the families get the prepared cancellation mail with an optional note from the team. It can be reopened later.",
        max_h=1600,
    )
    p = j.go("/dojos/51/events/76/attendance/")
    j.shot(
        "attendance",
        "Attendance with health notes",
        "The champion's attendance list also shows the family's allergy and health notes, only for children with a confirmed place, and every view of them is recorded in the audit log. The answers to the sign-up questions are on each row, with the totals at the top.",
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
