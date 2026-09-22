from django.contrib import admin

from geo.widgets import BelgiumGISModelAdmin

from .models import Dojo, Mentor

admin.site.register(Dojo, BelgiumGISModelAdmin)
admin.site.register(Mentor)
