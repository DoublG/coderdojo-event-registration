"""The JavaScript catalog (the texts bundle.js's gettext() uses) at a URL a
browser can cache for a year: /jsi18n/<language>/<version>/.

The language is in the URL instead of coming from the cookie, so a response
only depends on its URL; the version is a hash of the compiled JavaScript
catalogs and the Django version, so new translations get a new URL.
The pages link to it with {% load js_catalog %}{% javascript_catalog_url %}.
"""

import functools
import hashlib
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import django
from django.conf import settings
from django.dispatch import receiver
from django.http import Http404, HttpRequest
from django.http.response import HttpResponseBase
from django.urls import reverse
from django.utils import translation
from django.utils.autoreload import file_changed
from django.views.decorators.cache import cache_control
from django.views.i18n import JavaScriptCatalog

ONE_YEAR = 365 * 24 * 60 * 60


def _catalog_files() -> Iterator[Path]:
    """Every compiled JavaScript catalog the site's languages can use: ours
    (LOCALE_PATHS) and Django's own, for each language and its base."""
    locales = set()
    for code, _name in settings.LANGUAGES:
        locales.add(translation.to_locale(code))
        locales.add(translation.to_locale(code.split("-")[0]))
    folders = [Path(path) for path in settings.LOCALE_PATHS] + [Path(django.__file__).parent / "conf" / "locale"]
    for folder in folders:
        for locale in sorted(locales):
            path = folder / locale / "LC_MESSAGES" / "djangojs.mo"
            if path.exists():
                yield path


@functools.cache
def catalog_version() -> str:
    digest = hashlib.sha256(django.get_version().encode())
    for path in _catalog_files():
        digest.update(str(path).encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()[:12]


@receiver(file_changed)
def _forget_version_on_new_translations(sender: Any, file_path: Path, **kwargs: Any) -> None:
    # runserver doesn't restart for a .mo file (Django only drops its own
    # translation caches), so a compilemessages would otherwise keep the old URL.
    if file_path.suffix == ".mo":
        catalog_version.cache_clear()


def catalog_url(language: str | None = None) -> str:
    language = language or translation.get_language()
    if language not in dict(settings.LANGUAGES):
        language = settings.LANGUAGE_CODE
    return reverse("javascript-catalog-versioned", kwargs={"language": language, "version": catalog_version()})


@cache_control(public=True, max_age=ONE_YEAR, immutable=True)
def javascript_catalog(request: HttpRequest, language: str, version: str) -> HttpResponseBase:
    """Serves the current catalog whatever the version in the URL: an old
    version is only ever asked for by a page from before a deploy."""
    if language not in dict(settings.LANGUAGES):
        raise Http404
    with translation.override(language):
        return JavaScriptCatalog.as_view()(request)
