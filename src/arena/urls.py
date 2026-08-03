from django.contrib import admin
from django.urls import include, path

admin.site.site_header = "Documentos Arena"
admin.site.site_title = "Documentos Arena"
admin.site.index_title = "Administração"

urlpatterns = [
    path("admin/", admin.site.urls),
    path("contas/", include("django.contrib.auth.urls")),
    path("solicitacoes/", include("solicitacoes.urls")),
    path("analise/", include("analise.urls")),
    path("compliance/", include("compliance.urls")),
    path("credito/", include("credito.urls")),
    path("", include("operacoes.urls")),
]

# A pasta de uploads NÃO é servida como estático, nem em desenvolvimento: são
# documentos de identidade. Todo acesso passa por uma view que confere permissão
# e registra o download na auditoria (AGENTS.md §5.4, §6).
