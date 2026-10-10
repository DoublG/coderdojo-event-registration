"""Profiling annotations that cost nothing where django-silk isn't on.

silk is a development tool (requirements-dev.txt, settings.SILK_ENABLED), so
code never imports it directly: that would fail in production, where it isn't
installed. `profile` is silk's `silk_profile` when silk is on, and otherwise
does nothing, both as a decorator and as a context manager:

    @profile()
    def home(request): ...

    with profile(name="dojo search"):
        ...
"""

from collections.abc import Callable
from typing import Any, Literal, TypeVar

from django.conf import settings

F = TypeVar("F", bound=Callable[..., Any])


class _NoProfile:
    """Stands in for silk_profile: returns the function unchanged, and does
    nothing around a block."""

    def __call__(self, func: F) -> F:
        return func

    def __enter__(self) -> "_NoProfile":
        return self

    def __exit__(self, *exc_info: object) -> Literal[False]:
        return False


def profile(name: str | None = None) -> Any:
    """silk_profile(name) while silk is on, else a no-op. Decided when it's
    called, which for a decorator is when the module is imported."""
    if settings.SILK_ENABLED:
        from silk.profiling.profiler import silk_profile

        return silk_profile(name=name)
    return _NoProfile()
