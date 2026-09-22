from django.contrib import admin

from .models import AdministrativeBoundary, Municipality
from .widgets import BelgiumGISModelAdmin

admin.site.register(AdministrativeBoundary, BelgiumGISModelAdmin)
admin.site.register(Municipality, BelgiumGISModelAdmin)
