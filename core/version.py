"""Which version of the site is running.

A release's version is its git tag, a CalVer number: year, month and the
release of that month (`2026.10.3`). The demo deploy picks the next one,
`scripts/deploy.sh` writes it into the BUILD_INFO file at the root of the
release (`version=`, next to `release=`, `commit=` and `built=`), and it's
tagged and released on GitHub once the deploy succeeded (scripts/CLAUDE.md,
"Versions"). Without a BUILD_INFO file (development, tests) the version is
`DEVELOPMENT`, and `checkout()` says which branch and commit the working
tree has, read from `.git` on every call (cheap: a few small files), so a
branch switch shows without a restart.

The build info is read once per process: a deploy reloads every web and
Celery worker."""

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


def _git_dir(base: Path) -> Path | None:
    """The checkout's git directory: `.git` itself, or where a worktree's
    `.git` file points."""
    dot_git = base / ".git"
    if dot_git.is_dir():
        return dot_git
    text = dot_git.read_text(encoding="utf-8").strip() if dot_git.is_file() else ""
    if not text.startswith("gitdir:"):
        return None
    git_dir = Path(text.removeprefix("gitdir:").strip())
    return git_dir if git_dir.is_absolute() else base / git_dir


def _resolve(git_dir: Path, ref: str) -> str:
    """A ref's commit: its own file, or its line in packed-refs. A worktree
    keeps its refs in the main repository's git directory (`commondir`)."""
    common = git_dir
    if (git_dir / "commondir").is_file():
        common = git_dir / (git_dir / "commondir").read_text(encoding="utf-8").strip()
    for folder in (git_dir, common):
        if (folder / ref).is_file():
            return (folder / ref).read_text(encoding="utf-8").strip()
    packed = common / "packed-refs"
    if packed.is_file():
        for line in packed.read_text(encoding="utf-8").splitlines():
            commit, _, name = line.partition(" ")
            if name == ref:
                return commit
    return ""


def checkout() -> str:
    """`branch @ short commit` of the working tree in development (or just
    the commit when HEAD is detached), so a build that isn't a release says
    what it runs; empty when it's a release or there's no readable `.git`."""
    if not is_development():
        return ""
    try:
        git_dir = _git_dir(Path(settings.BASE_DIR))
        if git_dir is None:
            return ""
        head = (git_dir / "HEAD").read_text(encoding="utf-8").strip()
        if not head.startswith("ref:"):
            return head[:7]
        ref = head.removeprefix("ref:").strip()
        commit = _resolve(git_dir, ref)[:7]
    except OSError:
        return ""
    branch = ref.removeprefix("refs/heads/")
    return f"{branch} @ {commit}" if commit else branch
