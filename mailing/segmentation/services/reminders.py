from django.db.models import QuerySet

from users.models import User


class RegistrationReminderEligibility:

    @classmethod
    def users(cls) -> QuerySet:
        return User.objects.filter(
            registrations__status="incomplete",
            registrations__event__is_active=True,
        )

from accounts.models import User 

from ..base import SegmentAttribute, SegmentChoice


class RegistrationReminderEligibleAttribute(
    SegmentAttribute
):
    key = "registration_reminder_eligible"
    label = "Eligible for registration reminder"
    value_type = "boolean"

    def choices(self):
        return [
            SegmentChoice(True, "Yes"),
            SegmentChoice(False, "No"),
        ]

    def apply(self, queryset, operator, value):

        eligible = User.objects.all() #TODO get users filtered 

        if operator == "equals" and value:
            return queryset.filter(
                pk__in=eligible,
            )

        if operator == "equals" and not value:
            return queryset.exclude(
                pk__in=eligible,
            )

        raise ValueError(
            f"Unsupported operator: {operator}"
        )
