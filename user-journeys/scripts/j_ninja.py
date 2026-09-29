from lib import BASE, Journey, django, mail_ids, mail_shot, sync_playwright  # noqa: F401

with sync_playwright() as pw:
    django("from events.models import Registration as R; R.objects.filter(event_id=72, ninja_id=9).delete()")
    j = Journey("ninja", pw)
    j.login(
        "guardian-5-child-1",
        shoot_login=(
            "login",
            "Logging in with their own login",
            "A parent can give a child (7–17) a login of their own, with a password or login links (two-step login is possible too). The child logs in with the username the parent was given.",
        ),
    )
    p = j.go("/account/ninja/9/")
    j.shot(
        "me",
        "My belts, badges and history",
        "The ninja sees their current belt and who awarded it, their badges (with progress towards the next attendance wristband) and every session they came to. They can look, not edit: their details stay with the parent (the one thing they change themselves is their avatar, from the standard set).",
        max_h=2400,
    )
    p = j.go("/pathways/")
    if "404" in p.title() or p.locator("text=Page not found").count():
        p = j.go("/")
        p.locator("a[href^='/pathways/']").first.click()
        p.wait_for_load_state("networkidle")
    else:
        pass
    j.shot(
        "pathway",
        "Explore a learning pathway",
        "Pathways (Scratch, Python, web development, ...) show the steps and projects a ninja can work through at the dojo.",
        max_h=1800,
    )
    p = j.go("/events/72/")
    j.shot("event", "Find the next session", "The ninja browses sessions like anyone else ...")
    p = j.go("/events/72/signup/")
    boxes = p.locator("input[name=child]:not([disabled])")
    if boxes.count():
        boxes.first.check()
        j.shot(
            "signup",
            "... and signs themselves up",
            "With their own login a ninja can sign only themselves up. The parent still gets the confirmation mail.",
        )
        p.locator("form button[type=submit]").last.click()
        p.wait_for_load_state("networkidle")
        j.shot(
            "done",
            "Place confirmed",
            "The place is confirmed, and shows on the ninja's page and on the parent's account page, where either of them can cancel it.",
        )
    p = j.go("/account/security/")
    j.shot(
        "security",
        "Their own sign-in security",
        "A ninja's login has the same sign-in options as an adult's, two-step login included. The parent is told about every change.",
        max_h=1600,
    )
    j.save({"persona": "Ninja", "who": "guardian-5-child-1 (Lotte, 14, own login, home dojo Zonnebeke)"})
