"""Who sends with a mail template besides the site itself: the campaigns
app, which registers itself here from its AppConfig.ready() so the mail
engine imports none of it (CODING_STANDARDS.md, "Layers"). The Mail
templates pages show the names, and keep a template someone still needs."""

_USERS = []


def register(names_by_key, blocking):
    """`names_by_key()` → {template key: [what uses it]}, shown on the list;
    `blocking(key)` → whether something not yet sent still needs `key`."""
    _USERS.append((names_by_key, blocking))


def names_by_key():
    found = {}
    for names, _blocking in _USERS:
        for key, users in names().items():
            found.setdefault(key, []).extend(users)
    return found


def still_needed(key):
    return any(blocking(key) for _names, blocking in _USERS)
