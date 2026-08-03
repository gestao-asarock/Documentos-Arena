from django.urls import path

from . import views

app_name = "operacoes"

urlpatterns = [
    path("", views.lista, name="lista"),
    path("operacoes/nova/", views.nova, name="nova"),
    path("operacoes/<int:pk>/", views.detalhe, name="detalhe"),
    path("operacoes/<int:pk>/etapas/<int:etapa_id>/decidir/", views.decidir, name="decidir"),
    path("operacoes/<int:pk>/cancelar/", views.cancelar, name="cancelar"),
]
