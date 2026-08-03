from django.urls import path

from . import views

app_name = "credito"

urlpatterns = [
    path("", views.fila, name="fila"),
    path("<int:habilitacao_id>/", views.parecer, name="parecer"),
    path("<int:habilitacao_id>/evidencias/", views.anexar_evidencia, name="anexar_evidencia"),
    path("<int:habilitacao_id>/recusar/", views.recusar, name="recusar"),
]
