"""Where a family lives, from User.postal_code. A Belgian postcode can
cover several localities (geo.Municipality rows), so every test here asks
"does any municipality with this postcode match?"."""

from django.db.models import Exists, ExpressionWrapper, F, FloatField, OuterRef, Q

from dojos.models import Dojo
from geo.functions import DistanceSphere
from geo.models import AdministrativeBoundary, Municipality

from ..base import USER, SegmentAttribute, SegmentChoice, choice_q

BRUSSELS = "brussels"


def _in_province(province_ids):
    return Exists(AdministrativeBoundary.objects.filter(
        kind=AdministrativeBoundary.PROVINCE, pk__in=province_ids, boundary__contains=OuterRef("center"),
    ))


class ProvinceAttribute(SegmentAttribute):
    """The province of the family's postcode, or Brussels-Capital (which
    isn't a province, so it's the Brussels postcodes outside every
    province polygon). A handful of border localities fall outside every
    polygon too (e.g. 7040 Goegnies-Chaussée) and match no province."""

    key = "province"
    label = "Lives in province"
    value_type = "choice"
    scope = USER

    def choices(self):
        provinces = AdministrativeBoundary.objects.filter(kind=AdministrativeBoundary.PROVINCE).order_by("name")
        return [SegmentChoice(p.pk, p.name) for p in provinces] + [SegmentChoice(BRUSSELS, "Brussels-Capital Region")]

    def build_q(self, operator, value):
        values = [value] if operator == "equals" else value
        province_ids = [v for v in values if v != BRUSSELS]
        matched = Q(pk__in=[])
        if province_ids:
            matched |= Q(pk__in=Municipality.objects.filter(_in_province(province_ids)))
        if BRUSSELS in values:
            all_provinces = AdministrativeBoundary.objects.filter(kind=AdministrativeBoundary.PROVINCE)
            matched |= Q(pk__in=Municipality.objects.filter(postal_code__startswith="1").exclude(
                _in_province(all_provinces.values("pk"))
            ))
        postal_codes = Municipality.objects.filter(matched).values("postal_code")
        return choice_q("postal_code", "not_in" if operator == "not_in" else "in", postal_codes)


class LanguageAttribute(SegmentAttribute):
    key = "language"
    label = "Mail language"
    value_type = "choice"
    scope = USER

    def choices(self):
        from django.conf import settings

        return [SegmentChoice(code, name) for code, name in settings.LANGUAGES] + [SegmentChoice("", "Not set")]

    def build_q(self, operator, value):
        return choice_q("preferred_language", operator, value)


class NearDojoAttribute(SegmentAttribute):
    """The family's postcode is within `km` of a dojo (as the crow flies,
    from the postcode's municipality centres). Value: {"dojo": id, "km": n}."""

    key = "near_dojo"
    label = "Lives near dojo"
    value_type = "distance"
    scope = USER

    def choices(self):
        return [SegmentChoice(dojo.pk, dojo.name) for dojo in Dojo.objects.exclude(location=None).order_by("name")]

    def validate(self, operator, value):
        if operator not in self.operators:
            raise ValueError(f"“{self.label}” supports {', '.join(self.operators)}, not “{operator}”.")
        if not isinstance(value, dict) or not isinstance(value.get("km"), (int, float)) or value["km"] <= 0:
            raise ValueError('“Lives near dojo” needs a value like {"dojo": 12, "km": 25}.')
        if value.get("dojo") not in {choice.value for choice in self.choices()}:
            raise ValueError("Pick a dojo that has a location.")

    def describe(self, operator, value):
        names = {c.value: c.label for c in self.choices()}
        return f"Lives within {value.get('km')} km of {names.get(value.get('dojo'), 'a dojo')}"

    def value_from_form(self, operator, data):
        try:
            return {"dojo": int(data.get("dojo", "")), "km": float(data.get("km", ""))}
        except ValueError:
            return None

    def build_q(self, operator, value):
        if operator != "within":
            raise ValueError(f"Unsupported operator: {operator}")
        origin = Dojo.objects.get(pk=value["dojo"]).location
        nearby = Municipality.objects.annotate(
            distance_km=ExpressionWrapper(DistanceSphere(F("center"), origin) / 1000.0, output_field=FloatField())
        ).filter(distance_km__lte=value["km"])
        return Q(postal_code__in=nearby.values("postal_code"))
