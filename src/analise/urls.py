from django.urls import path

from . import views

app_name = "analise"

urlpatterns = [
    path("", views.fila, name="fila"),
    path("<int:documento_id>/", views.conferir, name="conferir"),
    path("<int:documento_id>/decidir/", views.decidir, name="decidir"),
    path("arquivos/<int:arquivo_id>/", views.baixar_arquivo, name="baixar_arquivo"),
]
