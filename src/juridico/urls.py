from django.urls import path

from . import views

app_name = "juridico"

urlpatterns = [
    path("", views.fila, name="fila"),
]
