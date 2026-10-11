from django.urls import path

from . import dojo_views, views

urlpatterns = [
    path("manage/reports/", views.report_list, name="manage_report_list"),
    path("manage/reports/new/<slug:dataset_key>/", views.report_create, name="manage_report_create"),
    path("manage/reports/data/<slug:dataset_key>/", views.report_data, name="manage_report_data"),
    path("manage/reports/data/<slug:dataset_key>/csv/", views.report_csv, name="manage_report_csv"),
    path("manage/reports/<int:report_id>/", views.report_detail, name="manage_report_detail"),
    path("manage/reports/<int:report_id>/delete/", views.report_delete, name="manage_report_delete"),
    # A dojo's champion: the reports the organisation shares, on the dojo's own figures.
    path("dojos/<int:dojo_id>/manage/reports/", dojo_views.dojo_report_list, name="dojo_report_list"),
    path(
        "dojos/<int:dojo_id>/manage/reports/<int:report_id>/", dojo_views.dojo_report_detail, name="dojo_report_detail"
    ),
    path(
        "dojos/<int:dojo_id>/manage/reports/data/<slug:dataset_key>/",
        dojo_views.dojo_report_data,
        name="dojo_report_data",
    ),
    path(
        "dojos/<int:dojo_id>/manage/reports/data/<slug:dataset_key>/csv/",
        dojo_views.dojo_report_csv,
        name="dojo_report_csv",
    ),
]
