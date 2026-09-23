"""
ASGI config for website project.

Routes plain HTTP through Django as usual and WebSocket connections through
Django Channels — see notifications/consumers.py and notifications/routing.py
for what actually lives behind ws://.../ws/dojos/<id>/notifications/.
"""

import os

import django
from channels.auth import AuthMiddlewareStack
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.security.websocket import AllowedHostsOriginValidator
from django.core.asgi import get_asgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'website.settings')
django.setup()

# Imported after django.setup(): notifications.routing (and the consumer it
# imports) touches Django models, which aren't ready until setup() has run.
from notifications.routing import websocket_urlpatterns  # noqa: E402

application = ProtocolTypeRouter({
    'http': get_asgi_application(),
    'websocket': AllowedHostsOriginValidator(
        AuthMiddlewareStack(URLRouter(websocket_urlpatterns))
    ),
})
