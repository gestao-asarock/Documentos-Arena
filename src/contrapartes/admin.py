from django.contrib import admin

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
    list_display = ("nome", "documento", "tipo_pessoa", "parte_relacionada", "ativa")
    list_filter = ("tipo_pessoa", "parte_relacionada", "ativa")
    search_fields = ("nome", "nome_fantasia", "documento")
    inlines = [DocumentoCadastralInline]


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
