from lib import BASE, Journey, django, mail_ids, mail_shot, sync_playwright  # noqa: F401

PAGES = [
    (
        "/manage/",
        "campaigns",
        "Campaigns",
        "Logging in (with two-step login) lands on the organisation dashboard. The sidebar groups its pages by area (Communication, Public site, Ninjas, Accounts, Organisation), and its switcher also lists the organisation's own events (Coolest Projects, CoderDojo Girlz). Campaigns are one-off mailings to a segment, with their results (queued, sent, bounced, suppressed).",
    ),
    (
        "/manage/campaigns/2/",
        "campaign",
        "A campaign",
        "Edit a draft, preview it in every language, see the audience count and a sample, send yourself a test, then launch (now or scheduled). The audience is frozen at launch.",
    ),
    ("/manage/segments/", "segments", "Segments", "Audiences described without code, with live counts."),
    (
        "/manage/segments/2/",
        "segment",
        "The segment builder",
        "Groups of rules about accounts or about 'the same child' (age, gender, belt, home dojo, engagement stage, distance to a dojo, ...), ANDed or ORed and nested. Child rules only reach guardians who consented.",
    ),
    (
        "/manage/journeys/",
        "journeys",
        "Journeys",
        "Standing campaigns that run daily, e.g. a 'we miss you' mail the week a child becomes at risk of dropping out.",
    ),
    (
        "/manage/templates/",
        "templates",
        "Mail templates",
        "Every mail the site sends, in English, Dutch and French, and what uses it.",
    ),
    (
        "/manage/mail/",
        "queue",
        "Mail queue",
        "Waiting and failed mail, bounces and blocked addresses, with a warning when the workers seem down. Failed mail is sent again with one click (one by one or all at once), an address is blocked by hand when someone asks us to stop, and unblocked once it works again.",
    ),
    (
        "/manage/mail/log/",
        "mail-log",
        "Mail log",
        "Every mail the site sent, newest first, searchable by address or subject and filtered by status or kind: to answer 'did they get our mail?'. A mail's text isn't shown, since some hold a personal login link.",
    ),
    (
        "/manage/promotions/",
        "promotions",
        "Promotions",
        "Feature events (e.g. Coolest Projects) on the homepage and elsewhere, for a set period.",
    ),
    ("/manage/sponsors/", "sponsors", "Sponsors", "The homepage's 'Made possible by'."),
    (
        "/manage/awards/",
        "awards",
        "Awards",
        "Only the organisation defines badges: one-off badges dojos can award, and milestone badges earned by attendance (which can grant a belt).",
    ),
    (
        "/manage/privacy/",
        "privacy",
        "Privacy requests",
        "Find any account to export its data, change its email address or delete it, and see the accounts retention is holding back.",
    ),
    (
        "/manage/people/",
        "people",
        "People",
        "Who holds which organisation role (admin, board, reviewer), invitations for people without an account, and open Django admin access.",
    ),
    (
        "/manage/security/",
        "security",
        "Sign-in policy",
        "Which roles must use two-step login or passkeys, from which date; and turning off someone's two-step login when they've lost their phone.",
    ),
    (
        "/manage/audit-log/",
        "audit",
        "Audit log",
        "Who changed what, and who viewed sensitive data. Read-only; health and security fields are hidden.",
    ),
    (
        "/manage/django-admin/",
        "django-admin",
        "Django admin on request",
        "The Django admin is for technical fixes only: an organisation role asks for it with a reason and their password, for 12 hours, and the other admins are notified.",
    ),
]
with sync_playwright() as pw:
    j = Journey("organisation", pw)
    j.login("org-priya-nair")
    for path, key, title, text in PAGES:
        j.go(path)
        j.shot(key, title, text, max_h=2000)
    j.save({"persona": "Organisation admin", "who": "org-priya-nair (organisation admin role, two-step login)"})
