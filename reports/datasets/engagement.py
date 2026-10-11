"""Children and how they come to sessions: the nightly engagement snapshot
(events.NinjaEngagement, the overall row per child), the same table the
segment builder's engagement rules read."""

from typing import Any

from django.db.models import Count, Sum
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from accounts.models import Ninja
from dojos.models import Dojo
from events.models import NinjaEngagement

from .base import DIMENSION, MEASURE, YES_NO, Column, Dataset, choice_values, merge

ENGAGEMENT = "events.NinjaEngagement"

# Age bands rather than ages: a child's exact age plus a dojo is too close to
# pointing them out. Worked out from the year of birth. "07–09" with a zero:
# the viewer sorts the bands as text.
AGE_BANDS: dict[str, Any] = {
    "7-9": _("07–09"),
    "10-12": _("10–12"),
    "13-15": _("13–15"),
    "16-17": _("16–17"),
    "18+": _("18 and older"),
}


def age_band(birth_year: int | None, this_year: int) -> str | None:
    if birth_year is None:
        return None
    age = this_year - birth_year
    if age < 7:
        return None
    if age <= 9:
        return "7-9"
    if age <= 12:
        return "10-12"
    if age <= 15:
        return "13-15"
    if age <= 17:
        return "16-17"
    return "18+"


class EngagementDataset(Dataset):
    key = "engagement"
    label = _("Children and how they come")
    description = _(
        "Every child with an overall engagement stage, from last night's snapshot: their stage, main dojo and "
        "its province, age band and gender, with how many sessions they came to and were offered."
    )
    count_column = "ninjas"
    dojo_column = "main_dojo"
    dojo_lookup = "main_dojo"
    generalise_order = ["main_dojo", "has_upcoming", "age_band", "gender", "province", "stage"]
    columns = [
        Column(
            "stage",
            _("Engagement stage"),
            DIMENSION,
            (ENGAGEMENT, "stage"),
            choice_values(NinjaEngagement.STAGE_CHOICES),
        ),
        Column("main_dojo", _("Main dojo"), DIMENSION, (ENGAGEMENT, "main_dojo")),
        Column("province", _("Province"), DIMENSION, ("dojos.Dojo", "province")),
        Column("age_band", _("Age band"), DIMENSION, ("accounts.Ninja", "date_of_birth"), AGE_BANDS),
        Column("gender", _("Gender"), DIMENSION, ("accounts.Ninja", "gender"), choice_values(Ninja.GENDER_CHOICES)),
        Column("has_upcoming", _("Signed up for a session"), DIMENSION, (ENGAGEMENT, "has_upcoming"), YES_NO),
        Column("ninjas", _("Children"), MEASURE, (ENGAGEMENT, "ninja")),
        Column("attended_180d", _("Sessions attended (180 days)"), MEASURE, (ENGAGEMENT, "attended_180d")),
        Column("offered_180d", _("Sessions offered (180 days)"), MEASURE, (ENGAGEMENT, "offered_180d")),
        Column("attended_total", _("Sessions attended (all time)"), MEASURE, (ENGAGEMENT, "attended_total")),
        Column("no_shows_90d", _("No-shows (90 days)"), MEASURE, (ENGAGEMENT, "no_shows_90d")),
    ]

    def query_rows(self, dojo: Dojo | None = None) -> list[dict[str, Any]]:
        this_year = timezone.localdate().year
        overall = NinjaEngagement.objects.filter(dojo__isnull=True)
        if dojo is not None:
            overall = overall.filter(**{self.dojo_lookup: dojo})
        query = (
            overall.values(
                "stage",
                "main_dojo__name",
                "main_dojo__province__name",
                "ninja__gender",
                "ninja__date_of_birth__year",
                "has_upcoming",
            )
            .annotate(
                ninjas=Count("ninja", distinct=True),
                attended_180d=Sum("attended_180d"),
                offered_180d=Sum("offered_180d"),
                attended_total=Sum("attended_total"),
                no_shows_90d=Sum("no_shows_90d"),
            )
            .order_by()
        )
        rows = [
            {
                "stage": row["stage"],
                "main_dojo": row["main_dojo__name"],
                "province": row["main_dojo__province__name"],
                "age_band": age_band(row["ninja__date_of_birth__year"], this_year),
                "gender": row["ninja__gender"],
                "has_upcoming": str(row["has_upcoming"]),
                "ninjas": row["ninjas"],
                "attended_180d": row["attended_180d"],
                "offered_180d": row["offered_180d"],
                "attended_total": row["attended_total"],
                "no_shows_90d": row["no_shows_90d"],
            }
            for row in query
        ]
        # Several years of birth fall in one band: add them up.
        return merge(rows, self.dimensions, self.measures)
