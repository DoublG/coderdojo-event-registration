from lib import BASE, Journey, django, mail_ids, mail_shot, sync_playwright  # noqa: F401

with sync_playwright() as pw:
    j = Journey("reviewer", pw)
    j.login(
        "org-sofie-claes",
        shoot_token=(
            "login-2fa",
            "Two-step login",
            "Reviewers see criminal-record extracts, so this account signs in with a code from an authenticator app after the password (passkeys and backup codes work too). The organisation can require this per role.",
        ),
    )
    p = j.go("/manage/checks/")
    j.shot(
        "checks",
        "Background checks",
        "The reviewer lands on the Volunteers group, the only pages this role opens. The queue: documents waiting for review, checks waiting for a document, and expired or expiring checks.",
        max_h=2000,
    )
    p = j.go("/manage/checks/352/")
    j.shot(
        "check",
        "Reviewing one check",
        "One person's check: download the document, then validate or reject it. Either decision deletes the document immediately; only the decision, the reviewer and the expiry date are kept. Opening this page is recorded in the audit log.",
        max_h=2000,
    )
    p = j.go("/manage/applications/")
    j.shot(
        "applications",
        "Applications",
        "Mentor and champion applications, with the state of each applicant's background check.",
        max_h=1800,
    )
    p = j.go("/manage/applications/348/")
    j.shot(
        "application",
        "Deciding an application",
        "With a valid check the reviewer approves (an approved mentor can then join dojos; a champion can create one) or declines. Nobody decides on their own application or check.",
        max_h=2000,
    )
    j.save(
        {"persona": "Background-check reviewer", "who": "org-sofie-claes (organisation reviewer role, two-step login)"}
    )
