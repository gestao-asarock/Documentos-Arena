from django.contrib import admin

from .models import ExigenciaCadastral, SubtipoDocumento, TipoDocumento


@admin.register(SubtipoDocumento)
class SubtipoDocumentoAdmin(admin.ModelAdmin):
    list_display = ("nome", "tipo_documento", "tem_validade_propria", "ativo")
    list_filter = ("tipo_documento", "ativo")
    search_fields = ("nome",)


@admin.register(ExigenciaCadastral)
class ExigenciaCadastralAdmin(admin.ModelAdmin):
    """O kit cadastral por tipo de pessoa e faixa de valor (AGENTS.md §4.5)."""

    list_display = (
        "tipo_pessoa",
        "tipo_documento",
        "valor_minimo",
        "valor_maximo",
        "obrigatorio",
        "grupo_alternativo",
        "ativa",
    )
    list_filter = ("tipo_pessoa", "obrigatorio", "ativa")


@admin.register(TipoDocumento)
class TipoDocumentoAdmin(admin.ModelAdmin):
    list_display = (
        "nome",
        "escopo",
        "kit_cadastral_pj",
        "obrigatorio_no_kit",
        "dias_validade",
        "ativo",
    )
    list_filter = ("escopo", "kit_cadastral_pj", "ativo")
    search_fields = ("nome",)
