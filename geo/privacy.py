"""geo holds reference data only (DATA_MODEL.md §16, `privacy.registry`)."""

from privacy.registry import register_not_personal

from .models import AdministrativeBoundary, Municipality

register_not_personal(AdministrativeBoundary, "Belgium's provinces and regions")
register_not_personal(Municipality, "Belgium's postcodes and municipalities")
