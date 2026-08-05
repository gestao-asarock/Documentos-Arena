from django.urls import path

from . import views

app_name = "juridico"

urlpatterns = [
    path("", views.fila, name="fila"),
    path("<int:operacao_id>/", views.revisar, name="revisar"),
    path("<int:operacao_id>/decidir/", views.decidir, name="decidir"),
    path(
        "<int:operacao_id>/arquivos/<int:arquivo_id>/",
        views.baixar_arquivo,
        name="baixar_arquivo",
    ),
]
