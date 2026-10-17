from lib import BASE, Journey, django, laptop_question, mail_ids, mail_shot, sync_playwright  # noqa: F401

with sync_playwright() as pw:
    django("from events.models import Registration as R; R.objects.filter(event_id=2990, ninja_id=9).delete()")
    # Session 2990 asks the laptop question (sign-up questions, DATA_MODEL.md §29).
    laptop_question(2990)
    before = mail_ids("guardian-5@coderdojo-demo.example")
    j = Journey("parent", pw)
    p = j.go("/")
    j.shot(
        "home",
        "Discover CoderDojo",
        "A parent lands on the homepage. Featured events take turns at the top, one at a time, and the dojo finder and the upcoming-sessions carousel are right there, no account needed.",
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
        "Per child: details, belt, badges, sessions attended and upcoming, whether the child has a login of their own, and the child's guardians, where a parent invites another (the other parent, a grandparent).",
        max_h=2000,
    )
    p = j.go("/events/2990/")
    j.shot("event", "Pick a session", "The parent opens a session at the child's home dojo.")
    p = j.go("/events/2990/signup/")
    j.shot(
        "pick-children",
        "Choose which children go",
        "The sign-up page lists the family's children; the ones already signed up are marked.",
    )
    boxes = p.locator("input[name=child]:not([disabled])")
    if boxes.count():
        boxes.first.check()
        p.locator(".child-signup:has(input[name=child]:checked) input[type=radio][value=no]").first.check()
        j.shot(
            "picked",
            "Answer the dojo's questions and confirm",
            "Tick the children. When the dojo asks something, such as whether the child brings their own laptop, each ticked child gets the questions to answer with yes or no. Then confirm.",
        )
        p.locator("form button[type=submit]").last.click()
        p.wait_for_load_state("networkidle")
        j.shot(
            "confirmed",
            "Signed up",
            "The place is confirmed on the spot (or the child joins the waiting list), with the answers given, and a confirmation mail is queued.",
        )
    mail_shot(
        j,
        "guardian-5@coderdojo-demo.example",
        before,
        "mail",
        "The confirmation mail",
        "The booking confirmation arrives in the parent's chosen mail language (here Dutch), with the answers to the dojo's questions. In development every mail lands in Mailpit.",
    )
    reg = django(
        "from events.models import Registration as R; print(R.objects.get(event_id=2990, ninja_id=9).id)"
    ).strip().splitlines()[-1]
    p = j.go("/account/")
    p.locator(f"a[href='/account/registration/{reg}/answers/']").first.click()
    p.wait_for_load_state("networkidle")
    j.shot(
        "answers",
        "Changing the answers",
        "Until the session starts, Change answers next to each place lets the family change them (or answer a question the dojo added later). The dojo's team gets a notification.",
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
