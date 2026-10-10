"""Who sends with a mail template besides the site itself: the campaigns
app, which registers itself here from its AppConfig.ready() so the mail
engine imports none of it (CODING_STANDARDS.md, "Layers"). The Mail
templates pages show the names, and keep a template someone still needs."""

from collections.abc import Callable

NamesByKey = Callable[[], dict[str, list[str]]]
Blocking = Callable[[str], bool]

_USERS: list[tuple[NamesByKey, Blocking]] = []


def register(names_by_key: NamesByKey, blocking: Blocking) -> None:
    """`names_by_key()` → {template key: [what uses it]}, shown on the list;
    `blocking(key)` → whether something not yet sent still needs `key`."""
    _USERS.append((names_by_key, blocking))


def names_by_key() -> dict[str, list[str]]:
    found: dict[str, list[str]] = {}
    for names, _blocking in _USERS:
        for key, users in names().items():
            found.setdefault(key, []).extend(users)
    return found


def still_needed(key: str) -> bool:
    return any(blocking(key) for _names, blocking in _USERS)
