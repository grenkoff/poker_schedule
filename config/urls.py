"""Root URL configuration."""

from django.contrib import admin
from django.http import HttpResponse
from django.urls import include, path


def healthz(_request):
    return HttpResponse("ok", content_type="text/plain")


urlpatterns = [
    path("healthz", healthz),
    path("admin/", admin.site.urls),
    path("accounts/", include("allauth.urls")),
    path("profile/", include("apps.users.urls")),
    path("export/", include("apps.exports.urls")),
    path("", include("apps.filters.urls")),
    path("", include("apps.tournaments.urls")),
]
