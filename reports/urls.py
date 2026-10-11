from django.urls import path

from . import views

urlpatterns = [
    path("manage/reports/", views.report_list, name="manage_report_list"),
    path("manage/reports/new/<slug:dataset_key>/", views.report_create, name="manage_report_create"),
    path("manage/reports/data/<slug:dataset_key>/", views.report_data, name="manage_report_data"),
    path("manage/reports/data/<slug:dataset_key>/csv/", views.report_csv, name="manage_report_csv"),
    path("manage/reports/<int:report_id>/", views.report_detail, name="manage_report_detail"),
    path("manage/reports/<int:report_id>/delete/", views.report_delete, name="manage_report_delete"),
]
