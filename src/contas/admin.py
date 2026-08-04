from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import Usuario


@admin.register(Usuario)
class UsuarioAdmin(UserAdmin):
    list_display = ("username", "first_name", "last_name", "email", "papeis", "is_active")
    list_filter = ("is_active", "groups")
    search_fields = ("username", "first_name", "last_name", "email")

    @admin.display(description="papéis")
    def papeis(self, obj: Usuario) -> str:
        return ", ".join(g.name for g in obj.groups.all()) or "-"
