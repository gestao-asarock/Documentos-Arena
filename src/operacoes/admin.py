from django.contrib import admin

from .models import (
    EtapaAprovacao,
    ExigenciaDocumental,
    Operacao,
    RegraEnquadramento,
    TipoOperacao,
)


class ExigenciaDocumentalInline(admin.TabularInline):
    model = ExigenciaDocumental
    extra = 1


@admin.register(TipoOperacao)
class TipoOperacaoAdmin(admin.ModelAdmin):
    list_display = ("nome", "ativo")
    search_fields = ("nome",)


@admin.register(RegraEnquadramento)
class RegraEnquadramentoAdmin(admin.ModelAdmin):
    """A matriz de alçadas do guia, editável (AGENTS.md §4.4)."""

    list_display = (
        "tipo_operacao",
        "criterio",
        "valor_minimo",
        "valor_maximo",
        "exige_triagem",
        "exige_due_diligence",
        "exige_risco_credito",
        "exige_juridico",
        "exige_assinaturas",
        "exige_boletagem",
        "waiver",
        "implementada",
    )
    list_filter = ("tipo_operacao", "implementada", "ativa", "waiver")
    search_fields = ("criterio",)
    inlines = [ExigenciaDocumentalInline]


class EtapaAprovacaoInline(admin.TabularInline):
    model = EtapaAprovacao
    extra = 0
    fields = ("etapa", "status", "parecer", "decidida_por", "data_decisao")
    readonly_fields = ("etapa",)


@admin.register(Operacao)
class OperacaoAdmin(admin.ModelAdmin):
    list_display = ("id", "tipo_operacao", "contraparte", "valor_total", "status", "data_criacao")
    list_filter = ("status", "tipo_operacao")
    search_fields = ("descricao", "contraparte__nome", "contraparte__documento")
    autocomplete_fields = ("contraparte",)
    readonly_fields = ("regra", "data_criacao", "data_atualizacao")
    inlines = [EtapaAprovacaoInline]

    def get_readonly_fields(self, request, obj=None):
        campos = list(super().get_readonly_fields(request, obj))
        # Valor e tipo congelam após o início do processo (AGENTS.md D13).
        if obj and not obj.esta_em_rascunho:
            campos += ["valor_total", "tipo_operacao"]
        return campos
