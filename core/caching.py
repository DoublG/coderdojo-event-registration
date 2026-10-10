"""The site's shared data caches (CAPACITY.md, "Caching"): lists that are the
same for every visitor, kept in the cache's Redis and cleared when what
they're built from changes, so a change shows at once and the timeout is
only a safety net for writes that skip save() (QuerySet.update(),
bulk_create()).

    sponsors = cached("content:sponsors", lambda: list(Sponsor.objects.filter(is_public=True)), 3600)
    clear_on_change(["content:sponsors"], Sponsor)

Whole pages are never cached: every page carries its own CSP nonce and CSRF
token, and the nav is per account. Cache the data or a fragment instead,
and never anything that decides access.

Every read is counted as a hit or a miss per name (monitoring.recorder), so
/metrics/ shows how well each cache works."""

from collections.abc import Callable, Iterable
from typing import Any

from django.core.cache import cache
from django.db import models, transaction
from django.db.models.signals import post_delete, post_save

from monitoring import recorder

_MISSING = object()  # tells a miss from a cached None


def cached[T](key: str, build: Callable[[], T], timeout: int | Callable[[T], int], name: str | None = None) -> T:
    """The value under `key`, or build() stored for `timeout` seconds.
    `name` groups keys for the metrics (default: `key`); `timeout` may be a
    function of the built value (e.g. until the next promotion starts)."""
    value = cache.get(key, _MISSING)
    recorder.note_cache(name or key, hit=value is not _MISSING)
    if value is not _MISSING:
        return value
    built = build()
    cache.set(key, built, timeout(built) if callable(timeout) else timeout)
    return built


def clear(*keys: str) -> None:
    """Forget these keys: now, and again once the current transaction
    commits (a request in between could cache the old rows)."""
    names = list(keys)
    cache.delete_many(names)
    transaction.on_commit(lambda: cache.delete_many(names))


def clear_on_change(keys: Iterable[str], *senders: type[models.Model]) -> None:
    """Clear `keys` whenever a row of any of `senders` is saved or deleted."""
    keys = list(keys)

    def receiver(**kwargs: Any) -> None:
        clear(*keys)

    for model in senders:
        uid = f"core.caching:{model._meta.label}:{','.join(keys)}"
        post_save.connect(receiver, sender=model, weak=False, dispatch_uid=uid)
        post_delete.connect(receiver, sender=model, weak=False, dispatch_uid=f"{uid}:delete")
