"""Erasing a person: the right to erasure (GDPR art. 17) and the retention
job's deletions (DATA_MODEL.md §16 phases 4 and 5).

Built from the classification only (`privacy.registry`), like the export: a
row is the person's when a model's `subjects` lookup points at the account,
at a child erased with it, or at the account's email address, and each of
its fields is treated as classified:

- `personal`: emptied (null, empty, False or the default; a file is deleted,
  a standard library image only unlinked). A required link to the person
  deletes the row: it's about them.
- `anonymise`: replaced ("{pk}" is the row's id; a `Computed` is worked out
  per row).
- `keep`: stays, for the reason given.

A row of someone else's that only links to the person (the account that
cancelled a place, a reviewer) gets that link's rule alone. The `User` and
`Ninja` rows themselves are anonymised, never deleted, so a past session's
team and its numbers stay right.

An adult account takes the children it's the only guardian of with it (and
their own logins); a child with another guardian stays with them.
`keep_visible` is the retention rule for champions and mentors: their name
as the site shows it is frozen into `display_name` and kept, and the
`public_profile` fields stay where they were shown (`visible_when`).

The audit log (§14) follows: entries about an erased row are cleared (on
request) or removed (retention), and so are those the account made. The
erasure itself isn't recorded there (its diff would hold what was erased);
an `ErasureRecord` per account and child is, without personal data, so
`manage.py privacy_replay_erasures` can erase them again after a backup is
restored.
"""

from dataclasses import dataclass, field
from functools import reduce
from operator import or_

from auditlog.context import disable_auditlog
from auditlog.models import LogEntry as AuditLogEntry
from django.contrib.admin.models import LogEntry as AdminLogEntry
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ImproperlyConfigured
from django.db import models, transaction
from django.db.models import Q

from accounts.models import Ninja, User
from core.image_library import is_library_image
from privacy import registry
from privacy.models import ErasureRecord
from privacy.registry import Category, Computed, Erasure, Subject

# Handled here rather than row by row: the logs of changes (by the content
# type and id of what they're about) and login sessions (they end with the
# password).
_HANDLED_SEPARATELY = {AuditLogEntry, AdminLogEntry}


def sole_children(user):
    """The children only `user` is a guardian of: erased with the account."""
    return [child for child in Ninja.objects.of_guardian(user) if child.guardianships.count() == 1]


def erase_person(user, requested_by=None, reason=ErasureRecord.REQUEST, keep_visible=False, *, replay=False):
    """Erase `user`, the children only they are a guardian of, and those
    children's own logins. Returns the erased children."""
    from dojos.team import end_all_memberships

    with transaction.atomic(), disable_auditlog():
        children = [] if user.is_ninja else sole_children(user)
        accounts = [user, *(User.objects.filter(ninja__in=children))]
        for account in accounts:
            end_all_memberships(account)
        if keep_visible:
            # The name past sessions' teams and awarded belts show.
            user.display_name = user.team_name
            User.objects.filter(pk=user.pk).update(display_name=user.display_name)
        _Erasure(accounts, children, keep_visible=keep_visible, delete_audit=reason == ErasureRecord.RETENTION).run()
        if not replay:
            _record(User, [user], reason, requested_by, keep_visible)
            _record(User, accounts[1:], reason, requested_by)
            _record(Ninja, children, reason, requested_by)
    return children


def erase_child(ninja, requested_by=None, reason=ErasureRecord.REQUEST, *, replay=False):
    """Erase one child and their own login, whatever guardians they have."""
    from dojos.team import end_all_memberships

    with transaction.atomic(), disable_auditlog():
        accounts = list(User.objects.filter(ninja=ninja))
        for account in accounts:
            end_all_memberships(account)
        _Erasure(accounts, [ninja], delete_audit=reason == ErasureRecord.RETENTION).run()
        if not replay:
            _record(User, accounts, reason, requested_by)
            _record(Ninja, [ninja], reason, requested_by)


def is_erased(user):
    return ErasureRecord.objects.filter(model=User._meta.label, object_id=user.pk).exists()


def replay_erasures():
    """Erase again everyone in the erasure log (after restoring a backup).
    Returns how many were found; rows that no longer exist are skipped."""
    done = 0
    for record in ErasureRecord.objects.order_by("erased_at", "pk"):
        if record.model == User._meta.label:
            if (user := User.objects.filter(pk=record.object_id).first()) is not None:
                erase_person(user, reason=record.reason, keep_visible=record.keep_visible, replay=True)
                done += 1
        elif record.model == Ninja._meta.label:
            if (ninja := Ninja.objects.filter(pk=record.object_id).first()) is not None:
                erase_child(ninja, reason=record.reason, replay=True)
                done += 1
    return done


def _record(model, objs, reason, requested_by, keep_visible=False):
    ErasureRecord.objects.bulk_create(
        ErasureRecord(
            model=model._meta.label,
            object_id=obj.pk,
            reason=reason,
            requested_by=requested_by,
            keep_visible=keep_visible,
        )
        for obj in objs
    )


@dataclass
class _Erasure:
    accounts: list
    children: list
    keep_visible: bool = False
    delete_audit: bool = False
    # (entry, obj) for the rows that are the person's, and (entry, obj,
    # field name) for others' rows that link to them.
    rows: list = field(default_factory=list)
    links: list = field(default_factory=list)

    def run(self):
        # Every row is found before anything changes: erasing clears the
        # very fields (an email address, a child's login) others are found by.
        self._collect()
        self._clear_logs()
        for entry, obj in self.rows:
            self._erase_row(entry, obj)
        for entry, obj, name in self.links:
            self._erase_link(entry, obj, name)

    # --- finding the rows -----------------------------------------------------

    def _collect(self):
        account_ids = [account.pk for account in self.accounts]
        child_ids = [child.pk for child in self.children]
        emails = [account.email for account in self.accounts if account.email]
        targets = {User: account_ids, Ninja: child_ids}
        for entry in registry.registered():
            if entry.model in _HANDLED_SEPARATELY:
                continue
            conditions = []
            for subject, lookup in entry.subjects.items():
                if subject == Subject.ACCOUNT and account_ids:
                    conditions.append(Q(**{f"{lookup}__in": account_ids}))
                elif subject == Subject.CHILD and child_ids:
                    conditions.append(Q(**{f"{lookup}__in": child_ids}))
                elif subject == Subject.EMAIL and emails:
                    conditions.append(reduce(or_, (Q(**{f"{lookup}__iexact": email}) for email in emails)))
            own = set()
            if conditions:
                for obj in entry.model._base_manager.filter(reduce(or_, conditions)).distinct().order_by("pk"):
                    own.add(obj.pk)
                    self.rows.append((entry, obj))
            for name, spec in entry.fields.items():
                model_field = entry.model._meta.get_field(name)
                ids = targets.get(model_field.related_model) if model_field.is_relation else None
                if not ids or model_field.many_to_many or spec.on_erasure == Erasure.KEEP:
                    continue
                for obj in entry.model._base_manager.filter(**{f"{name}__in": ids}).exclude(pk__in=own):
                    self.links.append((entry, obj, name))

    # --- erasing them --------------------------------------------------------

    def _erase_row(self, entry, obj):
        if self._about_them(entry, obj):
            _delete(entry, obj)
            return
        visible = self.keep_visible and (not entry.visible_when or getattr(obj, entry.visible_when))
        changed = {}
        for name, spec in entry.fields.items():
            if spec.on_erasure == Erasure.KEEP:
                continue
            if self.keep_visible and entry.model is User and name == "display_name":
                continue  # frozen by erase_person
            if visible and spec.category == Category.PUBLIC_PROFILE:
                continue
            model_field = entry.model._meta.get_field(name)
            if spec.on_erasure == Erasure.ANONYMISE:
                _set(obj, model_field, _replacement(spec.replacement, obj))
            else:
                _empty(obj, model_field)
            if not model_field.many_to_many:
                changed[model_field.attname] = getattr(obj, model_field.attname)
        _update(entry, obj, changed)

    def _about_them(self, entry, obj):
        """A required link to the person classified `personal`: the row is
        theirs and goes (a guardianship, a mail preference, a belt)."""
        targets = {User: {a.pk for a in self.accounts}, Ninja: {c.pk for c in self.children}}
        for name, spec in entry.fields.items():
            model_field = entry.model._meta.get_field(name)
            if (
                spec.on_erasure == Erasure.DELETE
                and model_field.is_relation
                and not model_field.many_to_many
                and not model_field.null
                and getattr(obj, model_field.attname) in targets.get(model_field.related_model, ())
            ):
                return True
        return False

    def _erase_link(self, entry, obj, name):
        spec = entry.fields[name]
        model_field = entry.model._meta.get_field(name)
        if spec.on_erasure == Erasure.DELETE and not model_field.null:
            _delete(entry, obj)
            return
        if spec.on_erasure == Erasure.ANONYMISE:
            _set(obj, model_field, _replacement(spec.replacement, obj))
        else:
            _empty(obj, model_field)
        _update(entry, obj, {model_field.attname: getattr(obj, model_field.attname)})

    def _clear_logs(self):
        """The audit log's and the admin history's entries about the
        person's rows, and the audit entries the accounts made."""
        about = Q(pk__in=[])
        admin_about = Q(pk__in=[])
        by_type = {}
        for entry, obj in self.rows:
            by_type.setdefault(entry.model, []).append(obj.pk)
        for model, pks in by_type.items():
            content_type = ContentType.objects.get_for_model(model, for_concrete_model=False)
            concrete_type = ContentType.objects.get_for_model(model)
            texts = [str(pk) for pk in pks]
            about |= Q(content_type__in=[content_type, concrete_type], object_pk__in=texts)
            admin_about |= Q(content_type__in=[content_type, concrete_type], object_id__in=texts)
        # The Background checks admin records through the User proxy.
        if users := by_type.get(User):
            from applications.models import BackgroundCheck

            proxy_type = ContentType.objects.get_for_model(BackgroundCheck, for_concrete_model=False)
            about |= Q(content_type=proxy_type, object_pk__in=[str(pk) for pk in users])
        by_them = Q(actor__in=[account.pk for account in self.accounts])
        if self.delete_audit:
            AuditLogEntry.objects.filter(about | by_them).delete()
        else:
            AuditLogEntry.objects.filter(about).update(
                object_repr="", changes=None, changes_text="", serialized_data=None, additional_data=None
            )
            AuditLogEntry.objects.filter(by_them).update(actor_email=None)
        AdminLogEntry.objects.filter(admin_about).update(object_repr="", change_message="")


# Through the queryset, not save()/delete() on the row: a row an earlier
# deletion already took with it (a cascade) is simply skipped, and no
# model's save() adds values of its own.
def _delete(entry, obj):
    entry.model._base_manager.filter(pk=obj.pk).delete()


def _update(entry, obj, values):
    if values:
        entry.model._base_manager.filter(pk=obj.pk).update(**values)


def _replacement(replacement, obj):
    if isinstance(replacement, Computed):
        return replacement.function(obj)
    if isinstance(replacement, str):
        return replacement.format(pk=obj.pk)
    return replacement


def _set(obj, model_field, value):
    if model_field.many_to_many:
        if value:
            raise ImproperlyConfigured(f"privacy: {model_field}: a many-to-many field can only be emptied")
        getattr(obj, model_field.name).clear()
    else:
        setattr(obj, model_field.attname, value)


def _empty(obj, model_field):
    """The field's empty value: null where allowed, else False, the default
    or an empty text. A file is deleted, unless it's a shared library image."""
    if model_field.many_to_many:
        getattr(obj, model_field.name).clear()
        return
    if isinstance(model_field, models.FileField):
        fieldfile = getattr(obj, model_field.name)
        if fieldfile and not is_library_image(fieldfile):
            fieldfile.delete(save=False)
        setattr(obj, model_field.attname, None if model_field.null else "")
    elif model_field.null:
        setattr(obj, model_field.attname, None)
    elif isinstance(model_field, models.BooleanField):
        setattr(obj, model_field.attname, False)
    elif model_field.has_default():
        setattr(obj, model_field.attname, model_field.get_default())
    elif isinstance(model_field, (models.CharField, models.TextField)):
        setattr(obj, model_field.attname, "")
    else:
        raise ImproperlyConfigured(f"privacy: {model_field} has no empty value; classify it differently")
