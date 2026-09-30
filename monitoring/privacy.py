"""Personal data in monitoring's models (DATA_MODEL.md §16, `privacy.registry`)."""

from privacy.registry import register_not_personal

from .models import CapacitySample

register_not_personal(CapacitySample, "table sizes, counters and process memory: nothing about a person")
