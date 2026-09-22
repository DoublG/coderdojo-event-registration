from django.urls import path

from . import views

urlpatterns = [
    path("register/dojo/", views.register_dojo, name="register_dojo"),
    path("register/helper/", views.register_helper, name="register_helper"),
]
