from lib import BASE, Journey, django, mail_ids, mail_shot, sync_playwright  # noqa: F401

with sync_playwright() as pw:
    django("from events.models import Registration as R; R.objects.filter(event_id=76).update(attended=None)")
    j = Journey("volunteer", pw)
    p = j.go("/register/")
    j.shot(
        "register",
        "Volunteer with us",
        "The sign-up page explains the ways in: a family account, helping at a dojo as a mentor, or starting a dojo as a champion. Volunteers use a normal account first.",
        max_h=1800,
    )
    j.login("guardian-11")
    p = j.go("/register/helper/")
    j.shot(
        "apply-mentor",
        "Apply to become a mentor",
        "Logged in, any adult can apply to become a mentor: optionally naming a dojo, their skills and availability, and agreeing to the background check. Mentor approval is once per account, not per dojo.",
        max_h=2200,
    )
    p = j.go("/register/dojo/")
    j.shot(
        "apply-champion",
        "Or apply to start a dojo",
        "Starting a dojo is the champion application: area, proposed venue and schedule. An approved champion creates their dojo themselves.",
        max_h=2200,
    )
    j.logout()
    j.login("guardian-2")
    p = j.go("/account/")
    j.shot(
        "check-requested",
        "The background check is requested",
        "After the application, a reviewer asks for the Belgian extract from the criminal record (model 2). The account page and a mailed link both lead to the upload.",
        max_h=2400,
    )
    p = j.go("/account/background-check/renew/")
    j.shot(
        "upload",
        "Uploading the document",
        "The document is stored privately (no public URL), seen only by the reviewers, and deleted as soon as they decide: only the decision is kept.",
        max_h=1600,
    )
    j.logout()
    j.login("guardian-3")
    p = j.go("/account/")
    j.shot(
        "waiting",
        "Waiting for review",
        "Once uploaded, the account shows the check is waiting for a reviewer. Reviewers get a daily mail while documents wait.",
        max_h=2400,
    )
    # an approved mentor at work
    j.logout()
    j.login("mentor-51-1")
    p = j.page
    j.shot(
        "landing",
        "An approved mentor logs in",
        "Once approved and on a dojo's team, logging in goes straight to the dojo's management area. The switcher at the top of the sidebar lists every dojo they help at.",
        max_h=1600,
    )
    p = j.go("/dojos/51/events/")
    j.shot(
        "events",
        "The dojo's sessions",
        "Mentors see and manage the dojo's sessions: publish, close registrations, reopen.",
        max_h=1600,
    )
    p = j.go("/dojos/51/events/76/")
    j.shot(
        "event",
        "One session",
        "The session's details, status, team and pathways, edited in place, plus a link to take attendance.",
        max_h=2200,
    )
    p = j.go("/dojos/51/events/76/attendance/")
    j.shot(
        "attendance",
        "Taking attendance at the door",
        "On the day, the mentor marks each child present or absent (htmx, no page reload). Each row shows the child's belt, engagement stage and a 'Visiting' label for children from another dojo; the session team is listed too, for the insurance.",
        max_h=2200,
    )
    btn = p.locator("button[value=present]").first
    if btn.count():
        btn.click()
        p.wait_for_timeout(1200)
        j.shot(
            "marked",
            "Marked present",
            "One click marks a child present and updates the 'N of M present' count. Milestone badges (wristbands) follow attendance automatically.",
            max_h=1400,
        )
    award = p.locator("details:has(select) > summary").first
    if award.count():
        award.scroll_into_view_if_needed()
        award.click()
        p.wait_for_timeout(600)
        j.shot(
            "belt",
            "Awarding a belt",
            "Mentors award belts and one-off badges from the same list. The belt history is append-only and records who awarded it and as which role.",
            full=False,
        )
    p = j.go("/dojos/51/manage/team/")
    j.shot(
        "team",
        "The dojo's team",
        "Every active mentor can accept join requests, add approved mentors and promote a ninja to youth mentor.",
        max_h=1800,
    )
    p = j.go("/dojos/3/")
    j.shot(
        "join",
        "Joining another dojo",
        "An approved mentor can ask to join any dojo's team from its public page; its team accepts or declines.",
        max_h=1800,
    )
    j.save(
        {
            "persona": "Volunteer (mentor)",
            "who": "guardian-11 / guardian-2 / guardian-3 (applicants) and mentor-51-1 (mentor at Dojo Westerlo)",
        }
    )
