from django.urls import path

from . import views

app_name = "operacoes"

urlpatterns = [
    path("", views.lista, name="lista"),
    path("operacoes/nova/", views.nova, name="nova"),
    path("operacoes/<int:pk>/", views.detalhe, name="detalhe"),
    path("operacoes/<int:pk>/etapas/<int:etapa_id>/decidir/", views.decidir, name="decidir"),
    path("operacoes/<int:pk>/cancelar/", views.cancelar, name="cancelar"),
    path("operacoes/<int:pk>/documentos/", views.vincular_documentos, name="vincular_documentos"),
    path("operacoes/<int:pk>/documentos/enviar/", views.enviar_documento, name="enviar_documento"),
    path("operacoes/<int:pk>/assinatura/", views.assinatura, name="assinatura"),
    path(
        "operacoes/<int:pk>/assinatura/<int:arquivo_id>/",
        views.baixar_para_assinatura,
        name="baixar_para_assinatura",
    ),
    path(
        "operacoes/<int:pk>/relatorios/<str:origem>/<int:relatorio_id>/",
        views.baixar_relatorio,
        name="baixar_relatorio",
    ),
    path(
        "operacoes/<int:pk>/documentos/<int:arquivo_id>/baixar/",
        views.baixar_documento,
        name="baixar_documento",
    ),
]
