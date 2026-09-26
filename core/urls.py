from django.urls import path

from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("contact/", views.contact, name="contact"),
    path("code-of-conduct/", views.code_of_conduct, name="code_of_conduct"),
]
