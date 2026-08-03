from django.contrib import admin

from .models import EventoAuditoria


@admin.register(EventoAuditoria)
class EventoAuditoriaAdmin(admin.ModelAdmin):
    """Somente leitura: trilha de auditoria não se edita nem se apaga (AGENTS.md §6)."""

    list_display = ("data_hora", "usuario", "acao", "descricao")
    list_filter = ("acao", "data_hora")
    search_fields = ("descricao",)
    date_hierarchy = "data_hora"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
