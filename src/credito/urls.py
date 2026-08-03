from django.urls import path

from . import views

app_name = "credito"

urlpatterns = [
    path("", views.fila, name="fila"),
    path("perfis/<int:habilitacao_id>/", views.parecer_perfil, name="parecer_perfil"),
    path(
        "perfis/<int:habilitacao_id>/recusar/",
        views.recusar_perfil_view,
        name="recusar_perfil",
    ),
    path("<int:operacao_id>/", views.parecer, name="parecer"),
    path("<int:operacao_id>/evidencias/", views.anexar_evidencia, name="anexar_evidencia"),
    path("<int:operacao_id>/recusar/", views.recusar, name="recusar"),
]
