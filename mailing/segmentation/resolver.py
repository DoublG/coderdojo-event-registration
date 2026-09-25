from functools import reduce
from operator import and_, or_

from django.db.models import Q

from accounts.models import Guardianship, Ninja, User

from ..models import SegmentGroup, SegmentRule
from .base import NINJA
from .registry import get_attribute


class SegmentResolver:
    """Turns a Segment into the accounts it describes.

    Every rule becomes its own `pk__in` subquery, never a join in one big
    filter(): two rules crossing the same to-many relation ("registered for
    event A" AND "registered for event B") would otherwise have to match
    the same registration row. Rules in a ninja group are combined on the
    child, so they all describe the same child, and the group then selects
    that child's guardians.

    The result is always active adult accounts with an email address:
    campaigns never go to ninja accounts. A segment without any rule
    resolves to nobody, never to everyone."""

    def resolve(self, segment):
        if not SegmentRule.objects.filter(group__segment=segment).exists():
            return User.objects.none()

        groups = list(segment.groups.prefetch_related("rules"))
        children = {}
        for group in groups:
            children.setdefault(group.parent_id, []).append(group)

        query = reduce(and_, (self._user_q(root, children) for root in children.get(None, [])), Q())

        return (
            User.objects
            .filter(is_active=True, account_type=User.ADULT)
            .exclude(email="")
            .filter(query)
        )

    def _user_q(self, group, children):
        """A Q on User for any group (a ninja group is projected to guardians)."""
        if group.scope == NINJA:
            ninjas = Ninja.objects.filter(self._ninja_q(group, children))
            return Q(pk__in=Guardianship.objects.filter(ninja__in=ninjas).values("guardian_id"))

        parts = [self._rule_q(rule, User) for rule in group.rules.all()]
        parts += [self._user_q(child, children) for child in children.get(group.pk, [])]
        return self._combine(group, parts)

    def _ninja_q(self, group, children):
        parts = [self._rule_q(rule, Ninja) for rule in group.rules.all()]
        for child in children.get(group.pk, []):
            if child.scope != NINJA:
                raise ValueError("A group inside a child group must also be about the child.")
            parts.append(self._ninja_q(child, children))
        return self._combine(group, parts)

    def _rule_q(self, rule, model):
        attribute = get_attribute(rule.attribute)
        expected = NINJA if model is Ninja else "user"
        if attribute.scope != expected:
            raise ValueError(f"“{attribute.label}” can't be used in a {expected} group.")
        return Q(pk__in=model.objects.filter(attribute.build_q(rule.operator, rule.value)).values("pk"))

    def _combine(self, group, parts):
        if not parts:
            return Q()
        if group.operator == SegmentGroup.Operator.AND:
            return reduce(and_, parts)
        if group.operator == SegmentGroup.Operator.OR:
            return reduce(or_, parts)
        raise ValueError(
            f"Unsupported group operator: {group.operator}"
        )
