from django.contrib import admin

from .codigo import normalizar_codigo
from .models import ArquivoDocumento, Contraparte, DocumentoCadastral, Habilitacao


@admin.register(Habilitacao)
class HabilitacaoAdmin(admin.ModelAdmin):
    list_display = ("contraparte", "status", "data_validade", "data_criacao")
    list_filter = ("status",)
    search_fields = ("contraparte__nome", "contraparte__documento")
    autocomplete_fields = ("contraparte",)


class DocumentoCadastralInline(admin.TabularInline):
    model = DocumentoCadastral
    extra = 0
    fields = ("tipo", "subtipo", "status", "data_emissao", "data_envio")
    readonly_fields = ("data_envio",)


@admin.register(Contraparte)
class ContraparteAdmin(admin.ModelAdmin):
    list_display = (
        "nome",
        "codigo_formatado",
        "documento",
        "tipo_pessoa",
        "parte_relacionada",
        "ativa",
    )
    list_filter = ("tipo_pessoa", "parte_relacionada", "ativa")
    # O código também se busca: é por ele que alguém vai chegar aqui vindo de um
    # e-mail ou de um telefonema, sem ter o CPF/CNPJ à mão (AGENTS.md D59).
    search_fields = ("nome", "nome_fantasia", "documento", "codigo")
    readonly_fields = ("codigo_formatado",)
    inlines = [DocumentoCadastralInline]

    @admin.display(description="código")
    def codigo_formatado(self, obj: Contraparte) -> str:
        return obj.codigo_formatado

    def get_search_results(self, request, queryset, search_term):
        """Aceita o código com hífen, do jeito que ele aparece na tela.

        `search_fields` compara o texto cru e o banco guarda o código sem
        pontuação: sem isto, copiar `K7M4-2QX9-BT5R` da tela e colar aqui não
        acharia nada (AGENTS.md D59).
        """
        if codigo := normalizar_codigo(search_term):
            return queryset.filter(codigo=codigo), False
        return super().get_search_results(request, queryset, search_term)


class ArquivoDocumentoInline(admin.TabularInline):
    model = ArquivoDocumento
    extra = 0
    fields = ("arquivo", "nome_original", "ordem", "data_envio")
    readonly_fields = ("data_envio",)


@admin.register(DocumentoCadastral)
class DocumentoCadastralAdmin(admin.ModelAdmin):
    list_display = ("rotulo", "contraparte", "status", "data_emissao", "esta_vigente")
    list_filter = ("status", "tipo")
    search_fields = ("contraparte__nome", "contraparte__documento")
    autocomplete_fields = ("contraparte",)
    inlines = [ArquivoDocumentoInline]

    @admin.display(boolean=True, description="vigente")
    def esta_vigente(self, obj: DocumentoCadastral) -> bool:
        return obj.esta_vigente
