from functools import reduce
from operator import and_, or_

from django.db.models import Q

from accounts.models import Guardianship, Ninja, User

from ..models import SegmentGroup
from .base import NINJA
from .registry import get_attribute


def serialize_segment(segment):
    """A segment's definition as plain data: what a Campaign freezes in
    `segment_snapshot` at launch, and what the resolver works on.

    {"name": ..., "groups": [{"scope", "operator", "rules": [{"attribute",
    "operator", "value"}], "children": [...]}]}, the root groups first."""
    groups = list(segment.groups.prefetch_related("rules").order_by("id"))
    children = {}
    for group in groups:
        children.setdefault(group.parent_id, []).append(group)

    def node(group):
        return {
            "scope": group.scope,
            "operator": group.operator,
            "rules": [
                {"attribute": rule.attribute, "operator": rule.operator, "value": rule.value}
                for rule in sorted(group.rules.all(), key=lambda r: r.pk)
            ],
            "children": [node(child) for child in children.get(group.pk, [])],
        }

    return {"name": segment.name, "groups": [node(root) for root in children.get(None, [])]}


def _has_rules(nodes):
    return any(n["rules"] or _has_rules(n["children"]) for n in nodes)


class SegmentResolver:
    """Turns a segment definition into the accounts it describes.

    Every rule becomes its own `pk__in` subquery, never a join in one big
    filter(): two rules crossing the same to-many relation ("registered for
    event A" AND "registered for event B") would otherwise have to match
    the same registration row. Rules in a ninja group are combined on the
    child, so they all describe the same child, and the group then selects
    that child's guardians: only those who agreed to the child's details
    being used for mail (accounts.consent).

    The result is always active adult accounts with an email address:
    campaigns never go to ninja accounts. A segment without any rule
    resolves to nobody, never to everyone."""

    def resolve(self, segment):
        return self.resolve_definition(serialize_segment(segment))

    def resolve_definition(self, definition):
        """The accounts for a serialized definition (serialize_segment), e.g. a
        campaign's frozen `segment_snapshot`."""
        roots = (definition or {}).get("groups", [])
        if not _has_rules(roots):
            return User.objects.none()
        query = reduce(and_, (self._user_q(root) for root in roots), Q())
        return (
            User.objects
            .filter(is_active=True, account_type=User.ADULT)
            .exclude(email="")
            .filter(query)
        )

    def _user_q(self, group):
        """A Q on User for any group (a ninja group is projected to guardians)."""
        if group["scope"] == NINJA:
            # Only the guardians who agreed to this child's details choosing
            # their mail (accounts.consent).
            ninjas = Ninja.objects.filter(self._ninja_q(group))
            consented = Guardianship.objects.filter(ninja__in=ninjas, consent_given_at__isnull=False)
            return Q(pk__in=consented.values("guardian_id"))

        parts = [self._rule_q(rule, User) for rule in group["rules"]]
        parts += [self._user_q(child) for child in group["children"]]
        return self._combine(group, parts)

    def _ninja_q(self, group):
        parts = [self._rule_q(rule, Ninja) for rule in group["rules"]]
        for child in group["children"]:
            if child["scope"] != NINJA:
                raise ValueError("A group inside a child group must also be about the child.")
            parts.append(self._ninja_q(child))
        return self._combine(group, parts)

    def _rule_q(self, rule, model):
        attribute = get_attribute(rule["attribute"])
        expected = NINJA if model is Ninja else "user"
        if attribute.scope != expected:
            raise ValueError(f"“{attribute.label}” can't be used in a {expected} group.")
        return Q(pk__in=model.objects.filter(attribute.build_q(rule["operator"], rule["value"])).values("pk"))

    def _combine(self, group, parts):
        if not parts:
            return Q()
        if group["operator"] == SegmentGroup.Operator.AND:
            return reduce(and_, parts)
        if group["operator"] == SegmentGroup.Operator.OR:
            return reduce(or_, parts)
        raise ValueError(
            f"Unsupported group operator: {group['operator']}"
        )
