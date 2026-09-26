"""A person's data export: right of access and portability (GDPR art. 15/20,
DATA_MODEL.md §16 phase 3).

Built from the classification only (`privacy.registry`): every model that
declares `subjects` contributes its rows that belong to the account, to the
children it's a guardian of, or to its email address. A row is exported
with all its fields except its id and the fields marked `export=False`
(secrets, the background-check document, links to someone else such as a
reviewer). Links show the linked object's name, so the file reads without
the database.
"""

import json
from functools import reduce
from operator import or_

from django.core.serializers.json import DjangoJSONEncoder
from django.db.models import FileField, Q
from django.utils import timezone

from accounts.models import Ninja
from privacy import registry
from privacy.registry import Subject, classifiable_fields


class _Encoder(DjangoJSONEncoder):
    def default(self, o):
        try:
            return super().default(o)
        except TypeError:
            return str(o)


def children_of(user):
    """The children whose data this login gets with its own: an adult's
    children, or a ninja login's own child record (never its siblings)."""
    if user.is_ninja:
        return Ninja.objects.filter(account=user)
    return Ninja.objects.of_guardian(user)


def _rows(entry, user, children):
    conditions = []
    for subject, lookup in entry.subjects.items():
        if subject == Subject.ACCOUNT:
            conditions.append(Q(**{lookup: user.pk}))
        elif subject == Subject.CHILD and children:
            conditions.append(Q(**{f"{lookup}__in": [child.pk for child in children]}))
        elif subject == Subject.EMAIL and user.email:
            conditions.append(Q(**{f"{lookup}__iexact": user.email}))
    if not conditions:
        return []
    return entry.model._base_manager.filter(reduce(or_, conditions)).distinct().order_by("pk")


def _value(obj, model_field):
    if model_field.many_to_many:
        return [str(related) for related in getattr(obj, model_field.name).all()]
    if model_field.is_relation:
        related = getattr(obj, model_field.name)
        return str(related) if related is not None else None
    value = getattr(obj, model_field.attname)
    if isinstance(model_field, FileField):
        return value.name or None
    return value


def _record(entry, obj):
    record = {}
    for model_field in classifiable_fields(entry.model):
        spec = entry.fields.get(model_field.name)
        if model_field.primary_key or (spec is not None and not spec.export):
            continue
        record[model_field.name] = _value(obj, model_field)
    return record


def export_person(user):
    """Everything the site keeps about this account and its children, as a dict."""
    children = list(children_of(user))
    data = {}
    for entry in registry.registered():
        if not entry.subjects:
            continue
        records = [_record(entry, obj) for obj in _rows(entry, user, children)]
        if records:
            data[entry.label] = {
                "name": str(entry.model._meta.verbose_name_plural),
                "purpose": entry.purpose,
                "records": records,
            }
    return {
        "generated_at": timezone.now(),
        "account": user.get_username(),
        "children": [child.name for child in children],
        "data": data,
    }


def export_json(user):
    return json.dumps(export_person(user), cls=_Encoder, indent=2, ensure_ascii=False)


def export_filename(user):
    return f"coderdojo-data-{user.get_username()}-{timezone.localdate():%Y-%m-%d}.json"
