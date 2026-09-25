from django.contrib.auth import get_user_model

from .registry import get_attribute


User = get_user_model()

from functools import reduce

from django.contrib.auth import get_user_model
from django.db.models import Q

from .registry import get_attribute


User = get_user_model()


class SegmentResolver:

    def resolve(self, segment):
        root_groups = segment.groups.filter(
            parent__isnull=True
        )

        query = Q()

        for group in root_groups:
            query &= self.build_group_q(group)

        return (
            User.objects
            .filter(
                is_active=True,
            )
            .filter(query)
            .distinct()
        )

    def build_group_q(self, group):
        parts = []

        # Rules directly inside this group
        for rule in group.rules.all():
            attribute = get_attribute(
                rule.attribute
            )

            parts.append(
                attribute.build_q(
                    rule.operator,
                    rule.value,
                )
            )

        # Nested groups
        for child in group.children.all():
            parts.append(
                self.build_group_q(child)
            )

        if not parts:
            return Q()

        if group.operator == "and":
            result = Q()

            for part in parts:
                result &= part

            return result

        if group.operator == "or":
            result = Q()

            for part in parts:
                result |= part

            return result

        raise ValueError(
            f"Unsupported group operator: {group.operator}"
        )

