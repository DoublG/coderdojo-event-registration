"""Which version of the site is running.

A release's version is its git tag, a CalVer number: year, month and the
release of that month (`2026.10.3`). The demo deploy picks the next one,
`scripts/deploy.sh` writes it into the BUILD_INFO file at the root of the
release (`version=`, next to `release=`, `commit=` and `built=`), and it's
tagged and released on GitHub once the deploy succeeded (scripts/CLAUDE.md,
"Versions"). Without a BUILD_INFO file (development, tests) the version is
`DEVELOPMENT`.

Read once per process: a deploy reloads every web and Celery worker."""

from functools import cache
from pathlib import Path

from django.conf import settings

DEVELOPMENT = "development"


def read_build_info(path: Path) -> dict[str, str]:
    """The `key=value` lines of a BUILD_INFO file; empty when there's none."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return {}
    info = {}
    for line in text.splitlines():
        key, sep, value = line.partition("=")
        if sep and key.strip():
            info[key.strip()] = value.strip()
    return info


@cache
def build_info() -> dict[str, str]:
    return read_build_info(Path(settings.BASE_DIR) / "BUILD_INFO")


def version() -> str:
    return build_info().get("version") or DEVELOPMENT


def is_development() -> bool:
    return version() == DEVELOPMENT
