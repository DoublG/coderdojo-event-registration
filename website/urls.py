"""website URL Configuration

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/3.1/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.conf import settings
from django.contrib import admin
from django.urls import path
from django.urls import include, path
from django.views.i18n import JavaScriptCatalog
from oauth2_provider import views as oauth2_views

from api.v1 import api as api_v1

urlpatterns = [
    path('admin/', admin.site.urls),
    path('i18n/', include('django.conf.urls.i18n')),  # provides the set_language view used by the menu's language switcher
    path('jsi18n/', JavaScriptCatalog.as_view(), name='javascript-catalog'),  # the texts bundle.js's gettext() uses
    path("", include("core.urls")),
    path("", include("accounts.urls")),
    path("", include("api.urls")),
    path("", include("applications.urls")),
    path("", include("dojos.urls")),
    path("", include("events.urls")),
    path("", include("pathways.urls")),
    path("", include("mailing.urls")),
    path("", include("content.urls")),
    path("", include("privacy.urls")),
    # The API (DATA_MODEL.md §13): OAuth 2.0 client credentials, then /api/v1/.
    path("api/oauth/token/", oauth2_views.TokenView.as_view(), name="oauth2_token"),
    path("api/oauth/revoke/", oauth2_views.RevokeTokenView.as_view(), name="oauth2_revoke"),
    path("api/v1/", api_v1.urls),
]

if settings.DEBUG:
    import debug_toolbar
    from django.conf.urls.static import static

    urlpatterns = [
        path('__debug__/', include(debug_toolbar.urls)),
    ] + urlpatterns + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
