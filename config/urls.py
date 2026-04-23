"""Root URL configuration.

Non-localized paths (healthz, admin, i18n setlang) sit outside i18n_patterns
so they have no language prefix. Everything user-facing is wrapped in
i18n_patterns and gets a /<lang>/ prefix for SEO and language detection.
"""

from django.conf.urls.i18n import i18n_patterns
from django.contrib import admin
from django.http import HttpResponse
from django.urls import include, path


def healthz(_request):
    return HttpResponse("ok", content_type="text/plain")


urlpatterns = [
    path("healthz", healthz),
    path("admin/", admin.site.urls),
    path("i18n/", include("django.conf.urls.i18n")),
]

urlpatterns += i18n_patterns(
    path("", include("apps.tournaments.urls")),
    prefix_default_language=True,
)
