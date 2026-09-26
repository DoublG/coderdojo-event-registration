from django.urls import path

from . import views

urlpatterns = [
    path("dojos/<int:dojo_id>/manage/api/", views.dojo_api_clients, name="dojo_api_clients"),
    path(
        "dojos/<int:dojo_id>/manage/api/<int:client_id>/renew/",
        views.dojo_api_client_renew,
        name="dojo_api_client_renew",
    ),
    path(
        "dojos/<int:dojo_id>/manage/api/<int:client_id>/delete/",
        views.dojo_api_client_delete,
        name="dojo_api_client_delete",
    ),
]
