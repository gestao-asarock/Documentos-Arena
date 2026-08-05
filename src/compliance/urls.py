from django.urls import path

from . import views

app_name = "compliance"

urlpatterns = [
    path("", views.fila, name="fila"),
    path("<int:habilitacao_id>/", views.parecer, name="parecer"),
    path("<int:habilitacao_id>/relatorios/", views.anexar_relatorio, name="anexar_relatorio"),
    path(
        "<int:habilitacao_id>/relatorios/<int:relatorio_id>/remover/",
        views.remover_relatorio,
        name="remover_relatorio",
    ),
    path("<int:habilitacao_id>/recusar/", views.recusar, name="recusar"),
]
