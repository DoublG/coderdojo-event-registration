"""Guardrails for uploaded files (CAPACITY.md, "Disk: files and uploads").

- Every uploaded image goes through `UploadedImageField`: at most
  MAX_UPLOAD_BYTES and MAX_IMAGE_PIXELS (checked by `validate_image_upload`,
  also in the Django admin), then, when the row is saved, made no larger than
  the field's `max_side` and re-encoded from its pixels alone: JPEG, or PNG
  when it has transparency. No metadata survives (EXIF with a phone photo's
  GPS position, XMP, comments, text chunks, colour profiles), after the
  orientation and the colour profile have been applied to the pixels.
- A replaced image, or one whose row is deleted, is deleted from storage once
  the transaction commits (`connect_cleanup`, from CoreConfig.ready).
- A standard image (core.image_library) is never processed or deleted: every
  row that uses one shares the same file.
- The background-check document: `validate_document_upload`, PDF, JPEG or PNG
  (by its first bytes, not its name) and at most MAX_UPLOAD_BYTES.

The proxy in front of the site refuses bodies over a little more than
MAX_UPLOAD_BYTES (client_max_body_size), so a larger file never reaches
Django; between the two limits the family sees this module's message."""

import io
import logging
import os

from django.apps import apps
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.db import models, transaction
from django.db.models.signals import post_delete, post_save, pre_save
from django.utils.text import format_lazy
from django.utils.translation import gettext_lazy as _
from PIL import Image, ImageOps

from .image_library import LIBRARY_PREFIX

logger = logging.getLogger(__name__)

MAX_UPLOAD_BYTES = 10 * 1024 * 1024
MAX_IMAGE_PIXELS = 40_000_000
JPEG_QUALITY = 85
# How big each kind of image is kept (its longest side, in pixels).
BANNER_SIDE = 1600
LOGO_SIDE = 800
ICON_SIDE = 512

IMAGE_UPLOAD_HELP = _("JPEG, PNG, GIF or WebP, at most 10 MB; it's made smaller to fit.")
DOCUMENT_UPLOAD_HELP = _("A PDF, JPEG or PNG file of at most 10 MB.")
# The first bytes of the document types a background-check extract comes in.
DOCUMENT_SIGNATURES = (b"%PDF-", b"\xff\xd8\xff", b"\x89PNG\r\n\x1a\n")


def with_upload_help(text=None):
    """A form's help text for an image upload: its own text, then the limits."""
    return format_lazy("{} {}", text, IMAGE_UPLOAD_HELP) if text else IMAGE_UPLOAD_HELP


def _is_new_upload(value):
    """Validators also run on a row's existing file (the admin re-validates
    the whole row); only a file that's being uploaded now is checked."""
    return bool(value) and not getattr(value, "_committed", False)


def _megabytes(size):
    return f"{size / 1024 / 1024:.1f}".rstrip("0").rstrip(".")


def validate_image_upload(value):
    if not _is_new_upload(value):
        return
    if value.size > MAX_UPLOAD_BYTES:
        raise ValidationError(
            _("The image is %(size)s MB; it can be at most %(max)s MB."),
            code="too_large",
            params={"size": _megabytes(value.size), "max": _megabytes(MAX_UPLOAD_BYTES)},
        )
    file = getattr(value, "file", value)
    position = file.tell()
    try:
        with Image.open(file) as image:  # reads the header only
            width, height = image.size
    except Exception:
        return  # not an image at all: the ImageField itself says so
    finally:
        file.seek(position)
    if width * height > MAX_IMAGE_PIXELS:
        raise ValidationError(
            _("The image is %(size)s megapixels; it can be at most %(max)s. Make it smaller and try again."),
            code="too_many_pixels",
            params={"size": round(width * height / 1_000_000), "max": MAX_IMAGE_PIXELS // 1_000_000},
        )


def validate_document_upload(value):
    if not _is_new_upload(value):
        return
    if value.size > MAX_UPLOAD_BYTES:
        raise ValidationError(
            _("The file is %(size)s MB; it can be at most %(max)s MB."),
            code="too_large",
            params={"size": _megabytes(value.size), "max": _megabytes(MAX_UPLOAD_BYTES)},
        )
    file = getattr(value, "file", value)
    position = file.tell()
    file.seek(0)
    start = file.read(16)
    file.seek(position)
    if not start.startswith(DOCUMENT_SIGNATURES):
        raise ValidationError(_("Upload a PDF, JPEG or PNG file."), code="file_type")


def _in_srgb(image, mode):
    """The image in `mode`, its colours converted to sRGB when it carries a
    colour profile of its own (a phone's Display P3, for one), so dropping
    the profile doesn't shift them."""
    profile = image.info.get("icc_profile")
    if profile:
        try:
            from PIL import ImageCms

            source = ImageCms.ImageCmsProfile(io.BytesIO(profile))
            converted = image.convert(mode) if image.mode != mode else image
            return ImageCms.profileToProfile(converted, source, ImageCms.createProfile("sRGB"), outputMode=mode)
        except Exception:
            logger.info("Couldn't apply an uploaded image's colour profile", exc_info=True)
    return image.convert(mode)


def shrink_image(file, max_side):
    """The image at most `max_side` pixels on its longest side, re-encoded
    from its pixels alone: (ContentFile, extension), or None when Pillow
    can't read it. Nothing of the original file's metadata survives: EXIF
    (camera, GPS position, date), XMP, comments, text chunks and colour
    profiles are all left out; the orientation and the colour profile are
    applied to the pixels first."""
    file.seek(0)
    try:
        with Image.open(file) as image:
            # A JPEG decodes straight at a reduced scale: a big photo never
            # takes its full size in memory.
            image.draft("RGB", (max_side, max_side))
            image = ImageOps.exif_transpose(image)
            transparent = image.mode in ("RGBA", "LA", "PA") or (image.mode == "P" and "transparency" in image.info)
            image.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)
            clean = _in_srgb(image, "RGBA" if transparent else "RGB")
            # Pillow writes some of `info` back when saving (a JPEG's comment,
            # a PNG's colour profile): the saved file gets none of it.
            clean.info = {}
            out = io.BytesIO()
            if transparent:
                clean.save(out, "PNG", optimize=True)
                extension = "png"
            else:
                clean.save(out, "JPEG", quality=JPEG_QUALITY, optimize=True, progressive=True)
                extension = "jpg"
    except Exception:
        logger.warning("Couldn't shrink an uploaded image; stored as it is", exc_info=True)
        return None
    return ContentFile(out.getvalue()), extension


def is_library_name(name):
    return bool(name) and name.startswith(f"{LIBRARY_PREFIX}/")


class UploadedImageField(models.ImageField):
    """An ImageField for images people upload: checked, shrunk to `max_side`
    and re-encoded when saved, and its file deleted when it's replaced or
    its row goes (see the module docstring)."""

    def __init__(self, *args, max_side=BANNER_SIDE, **kwargs):
        self.max_side = max_side
        kwargs.setdefault("validators", [validate_image_upload])
        super().__init__(*args, **kwargs)

    def deconstruct(self):
        name, path, args, kwargs = super().deconstruct()
        kwargs["max_side"] = self.max_side
        if kwargs.get("validators") == [validate_image_upload]:
            del kwargs["validators"]
        return name, path, args, kwargs

    def pre_save(self, model_instance, add):
        file = getattr(model_instance, self.attname)
        if file and not file._committed and not is_library_name(file.name):
            shrunk = shrink_image(file.file, self.max_side)
            if shrunk:
                content, extension = shrunk
                file.file = content
                file.name = f"{os.path.splitext(os.path.basename(file.name))[0]}.{extension}"
        return super().pre_save(model_instance, add)


# --- deleting files nobody uses any more ----------------------------------------------


def _upload_fields(model):
    return [field for field in model._meta.fields if isinstance(field, UploadedImageField)]


def _delete_later(model, field, name):
    """Delete `name` from the field's storage once the transaction commits,
    unless it's a standard image or another row still points at it."""
    if not name or is_library_name(name):
        return

    def delete():
        if model._base_manager.filter(**{field.attname: name}).exists():
            return
        try:
            field.storage.delete(name)
        except Exception:
            logger.warning("Couldn't delete the replaced file %s", name, exc_info=True)

    transaction.on_commit(delete)


def _remember_files(sender, instance, raw=False, update_fields=None, **kwargs):
    if raw or instance._state.adding or instance.pk is None:
        return
    fields = [f for f in _upload_fields(sender) if update_fields is None or f.name in update_fields]
    if not fields:
        return
    stored = sender._base_manager.filter(pk=instance.pk).values(*[f.attname for f in fields]).first() or {}
    instance._stored_files = {f.attname: stored.get(f.attname) for f in fields}


def _delete_replaced(sender, instance, raw=False, **kwargs):
    stored = instance.__dict__.pop("_stored_files", None)
    if raw or not stored:
        return
    for field in _upload_fields(sender):
        old = stored.get(field.attname)
        current = getattr(instance, field.attname)
        if old and old != (current.name if current else ""):
            _delete_later(sender, field, old)


def _delete_with_row(sender, instance, **kwargs):
    for field in _upload_fields(sender):
        current = getattr(instance, field.attname)
        if current:
            _delete_later(sender, field, current.name)


def connect_cleanup():
    """Only for the models with an UploadedImageField (proxies included): a
    receiver for every model would stop Django's fast bulk deletes."""
    for model in apps.get_models():
        if _upload_fields(model):
            uid = f"core.uploads:{model._meta.label}"
            pre_save.connect(_remember_files, sender=model, dispatch_uid=f"{uid}:pre", weak=False)
            post_save.connect(_delete_replaced, sender=model, dispatch_uid=f"{uid}:post", weak=False)
            post_delete.connect(_delete_with_row, sender=model, dispatch_uid=f"{uid}:delete", weak=False)
