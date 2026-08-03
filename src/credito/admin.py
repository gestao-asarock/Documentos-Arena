from django.contrib import admin

from .models import EvidenciaCredito, ParecerCredito


class EvidenciaInline(admin.TabularInline):
    model = EvidenciaCredito
    extra = 0
    readonly_fields = ("data_envio",)


@admin.register(ParecerCredito)
class ParecerCreditoAdmin(admin.ModelAdmin):
    list_display = ("habilitacao", "status", "veredito", "analista", "data_conclusao")
    list_filter = ("status", "veredito")
    search_fields = ("habilitacao__contraparte__nome", "habilitacao__contraparte__documento")
    inlines = [EvidenciaInline]
