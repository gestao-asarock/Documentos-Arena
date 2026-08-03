"""
Cria os grupos que representam os papéis (AGENTS.md §4.2).

Apenas os grupos: as permissões de cada um são atribuídas no Admin, para que a
área responsável possa ajustar sem depender de deploy.
"""

from django.db import migrations

PAPEIS = ["administrador", "crm", "compliance", "juridico", "clube"]


def criar_papeis(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    for nome in PAPEIS:
        Group.objects.get_or_create(name=nome)


def remover_papeis(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Group.objects.filter(name__in=PAPEIS).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("contas", "0001_initial"),
        ("auth", "0012_alter_user_first_name_max_length"),
    ]

    operations = [
        migrations.RunPython(criar_papeis, remover_papeis),
    ]
