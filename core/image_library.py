"""The standard images shipped with the app — event banners, dojo icons,
award icons, mentor and ninja avatars, pathway images — and how a model's
image field points at one of them.

A standard image is stored **once**, under MEDIA_ROOT/library/<kind>/<file>,
and every row that uses it just links to that same path: picking a template
never makes a new copy. Only a file someone uploads themselves goes through
the field's own `upload_to` (and gets its own copy, as before).

The library files are copied from the app's bundled source directories
(LIBRARY_DIRS) into media storage the first time each one is used, so
nothing has to run at deploy time. A library file is shared, so never
`.delete()` it through a model field — `is_library_image()` tells the two
apart.
"""

from pathlib import Path

from django.core.files import File
from django.core.files.storage import default_storage

from accounts.template_avatars import TEMPLATE_AVATARS_DIR, TEMPLATE_KID_AVATARS_DIR
from dojos.template_icons import TEMPLATE_ICONS_DIR
from events.template_images import TEMPLATE_IMAGES_DIR

BASE_DIR = Path(__file__).resolve().parent.parent

LIBRARY_PREFIX = "library"

# kind → the bundled directory its standard images come from.
LIBRARY_DIRS = {
    "events": TEMPLATE_IMAGES_DIR,
    "dojos": TEMPLATE_ICONS_DIR,
    "awards": BASE_DIR / "events" / "seed_data" / "awards",
    "mentors": TEMPLATE_AVATARS_DIR,
    "ninjas": TEMPLATE_KID_AVATARS_DIR,
    "pathways": BASE_DIR / "pathways" / "seed_data" / "images",
}


def _source(kind, filename):
    source = LIBRARY_DIRS[kind] / filename
    # Filenames come from form posts too: only a plain name of a file that
    # really is in the library, never a path out of it.
    if not filename or Path(filename).name != filename or not source.is_file():
        raise ValueError(f"No standard {kind} image named {filename!r}.")
    return source


def library_name(kind, filename):
    """The storage name a field is set to in order to use this standard
    image. Copies the file into media storage the first time it's needed."""
    source = _source(kind, filename)
    name = f"{LIBRARY_PREFIX}/{kind}/{filename}"
    if not default_storage.exists(name):
        with open(source, "rb") as f:
            saved = default_storage.save(name, File(f))
        if saved != name:
            # Someone else stored it in the meantime: keep theirs.
            default_storage.delete(saved)
    return name


def use_library_image(instance, field_name, kind, filename, save=False):
    """Point `instance.<field_name>` at a standard image (no copy made)."""
    setattr(instance, field_name, library_name(kind, filename))
    if save:
        instance.save(update_fields=[field_name])


def is_library_image(fieldfile):
    return bool(fieldfile) and fieldfile.name.startswith(f"{LIBRARY_PREFIX}/")


def library_filename(fieldfile, kind):
    """The standard image's filename if the field uses one of this kind
    (e.g. to preselect it in a picker), else None."""
    prefix = f"{LIBRARY_PREFIX}/{kind}/"
    if fieldfile and fieldfile.name.startswith(prefix):
        return fieldfile.name[len(prefix):]
    return None
