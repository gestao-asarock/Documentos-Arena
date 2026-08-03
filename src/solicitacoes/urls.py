from django.urls import path

from . import views

app_name = "solicitacoes"

urlpatterns = [
    path("", views.lista, name="lista"),
    path("nova/", views.nova, name="nova"),
    path("<int:pk>/", views.detalhe, name="detalhe"),
    path("<int:pk>/documentos/", views.enviar_documento, name="enviar_documento"),
    path("<int:pk>/arquivos/<int:arquivo_id>/", views.baixar_arquivo, name="baixar_arquivo"),
    path(
        "<int:pk>/documentos/<int:documento_id>/excluir/",
        views.excluir_documento,
        name="excluir_documento",
    ),
    path("<int:pk>/cancelar/", views.cancelar, name="cancelar"),
    path("cep/", views.buscar_cep, name="buscar_cep"),
]
