from django.contrib import admin

from geo.widgets import BelgiumGISModelAdmin

from .models import Award, Event, ParticipantAward, Registration

admin.site.register(Event, BelgiumGISModelAdmin)
admin.site.register(Registration)
admin.site.register(Award)
admin.site.register(ParticipantAward)
