from django.contrib import admin

from .models import Solicitacao


@admin.register(Solicitacao)
class SolicitacaoAdmin(admin.ModelAdmin):
    list_display = ("id", "descricao", "contraparte", "valor", "data_evento", "status")
    list_filter = ("status", "tipo_operacao")
    search_fields = ("descricao", "contraparte__nome", "contraparte__documento")
    autocomplete_fields = ("contraparte",)
    readonly_fields = ("data_criacao", "data_atualizacao")
