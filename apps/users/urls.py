from django.urls import path

from . import views

app_name = "users"

urlpatterns = [
    path("", views.profile, name="profile"),
    path("table-prefs/", views.save_table_prefs, name="save_table_prefs"),
]
