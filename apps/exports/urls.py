from django.urls import path

from . import views

app_name = "exports"

urlpatterns = [
    path("pdf/", views.export_pdf, name="pdf"),
]
