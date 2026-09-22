from django.urls import path

from . import views

urlpatterns = [
    path("pathways/<int:pathway_id>/", views.pathway_detail, name="pathway_detail"),
]
