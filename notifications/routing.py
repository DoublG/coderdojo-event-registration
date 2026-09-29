from django.urls import path

from . import consumers

websocket_urlpatterns = [
    path("ws/dojos/<int:dojo_id>/notifications/", consumers.NotificationConsumer.as_asgi()),
    path("ws/manage/notifications/", consumers.OrganisationNotificationConsumer.as_asgi()),
]
