"""Root URL configuration.

Non-localized paths (healthz, i18n setlang) sit outside i18n_patterns so they
have no language prefix. Everything user-facing is wrapped and gets a
/<lang>/ prefix for SEO and language detection.
"""

from django.conf.urls.i18n import i18n_patterns
from django.contrib import admin
from django.http import HttpResponse
from django.shortcuts import render
from django.urls import include, path
from django.utils.translation import gettext_lazy as _


def healthz(_request):
    return HttpResponse("ok", content_type="text/plain")


def home(request):
    return render(request, "home.html", {"page_title": _("Poker Schedule")})


urlpatterns = [
    path("healthz", healthz),
    path("i18n/", include("django.conf.urls.i18n")),
]

urlpatterns += i18n_patterns(
    path("admin/", admin.site.urls),
    path("", home, name="home"),
    prefix_default_language=True,
)
