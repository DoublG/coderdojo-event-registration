from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import ChildAccount, DojoOwner, Guardian, HelperAccount, Participant, User

admin.site.register(User, UserAdmin)
admin.site.register(DojoOwner, UserAdmin)
admin.site.register(Guardian, UserAdmin)
admin.site.register(ChildAccount, UserAdmin)
admin.site.register(HelperAccount, UserAdmin)
admin.site.register(Participant)
