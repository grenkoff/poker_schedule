from django.urls import path

from . import views

app_name = "filters"

urlpatterns = [
    path("share/create/", views.create_share, name="create_share"),
    path("s/<slug:slug>/", views.shared_view, name="shared"),
]
