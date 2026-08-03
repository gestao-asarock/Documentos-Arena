from django.contrib import admin

from .models import Solicitacao


@admin.register(Solicitacao)
class SolicitacaoAdmin(admin.ModelAdmin):
    """Perfil da contraparte (AGENTS.md D29)."""

    list_display = ("id", "contraparte", "status", "criada_por", "data_criacao")
    list_filter = ("status",)
    search_fields = ("contraparte__nome", "contraparte__documento")
    autocomplete_fields = ("contraparte",)
    readonly_fields = ("data_criacao", "data_atualizacao")
