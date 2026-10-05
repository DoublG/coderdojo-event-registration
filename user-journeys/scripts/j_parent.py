from lib import BASE, Journey, django, mail_ids, mail_shot, sync_playwright  # noqa: F401

with sync_playwright() as pw:
    django("from events.models import Registration as R; R.objects.filter(event_id=71, ninja_id=9).delete()")
    before = mail_ids("guardian-5@coderdojo-demo.example")
    j = Journey("parent", pw)
    p = j.go("/")
    j.shot(
        "home",
        "Discover CoderDojo",
        "A parent lands on the homepage. The dojo finder and the upcoming-sessions carousel are right there, no account needed.",
        max_h=1700,
    )
    p = j.go("/dojos/?location=Westerlo&pathway=2")
    j.shot(
        "finder",
        "Find a dojo nearby",
        "The dojo finder sorts dojos by distance from a typed address, the browser's location or (logged in) the family's postcode, and filters them by language and pathway; each applied filter shows as a chip that removes it.",
    )
    p = j.go("/dojos/51/")
    j.shot(
        "dojo",
        "A dojo's page",
        "Each dojo has a page with its languages, next sessions, team, updates and the pathways it offers.",
        max_h=1800,
    )
    p = j.go("/events/")
    j.shot(
        "events",
        "Browse sessions",
        "All upcoming sessions, near a place or not, filterable by dojo, date, age, language and pathway.",
    )
    p = j.go("/events/76/")
    j.shot(
        "event-full",
        "A full session",
        "When a session is full, families can still join the waiting list; they move up automatically when a place frees up.",
    )
    p = j.go("/register/guardian/")
    j.shot(
        "signup",
        "Create a family account",
        "Self-service sign-up: the parent's details, one row per child (add more with “Add another child”), mail language and optional consents. No approval needed.",
        max_h=2200,
    )
    j.login("guardian-5")
    p = j.go("/account/")
    j.shot(
        "account",
        "The family's account page",
        "After logging in, the account page shows the parent's details (edited in place), each child, their upcoming places (and waiting-list positions) and links to mail preferences, security and privacy.",
        max_h=2200,
    )
    p = j.go("/account/ninja/9/")
    j.shot(
        "child",
        "A child's page",
        "Per child: details, belt, badges, sessions attended and upcoming, and whether the child has a login of their own.",
        max_h=2000,
    )
    p = j.go("/events/71/")
    j.shot("event", "Pick a session", "The parent opens a session at the child's home dojo.")
    p = j.go("/events/71/signup/")
    j.shot(
        "pick-children",
        "Choose which children go",
        "The sign-up page lists the family's children; the ones already signed up are marked.",
    )
    boxes = p.locator("input[name=child]:not([disabled])")
    if boxes.count():
        boxes.first.check()
        j.shot("picked", "Confirm", "Tick the children and confirm.")
        p.locator("form button[type=submit]").last.click()
        p.wait_for_load_state("networkidle")
        j.shot(
            "confirmed",
            "Signed up",
            "The place is confirmed on the spot (or the child joins the waiting list), and a confirmation mail is queued.",
        )
    mail_shot(
        j,
        "guardian-5@coderdojo-demo.example",
        before,
        "mail",
        "The confirmation mail",
        "The booking confirmation arrives in the parent's chosen mail language (here Dutch). In development every mail lands in Mailpit.",
    )
    p = j.go("/account/mail/")
    j.shot(
        "mail-prefs",
        "Mail preferences",
        "The parent chooses which kinds of mail they get, mutes a dojo's news, and gives or withdraws consent per child.",
        max_h=2000,
    )
    p = j.go("/account/security/")
    j.shot(
        "security",
        "Sign-in security",
        "Optional two-step login (authenticator app, passkeys, backup codes), or switching to login links instead of a password.",
        max_h=1800,
    )
    p = j.go("/account/delete/")
    j.shot(
        "delete",
        "Privacy: export or delete",
        "From the account page the family downloads all its data, or deletes the account after confirming with the password.",
    )
    j.save({"persona": "Parent", "who": "guardian-5 (seeded parent of Lotte, 14, and Olivia, 16)"})
