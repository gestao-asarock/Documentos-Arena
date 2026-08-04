"""
Tira o travessão do nome do subtipo (AGENTS.md D49).

O nome é dado em tabela e aparece na tela; renomear é a única forma de tirá-lo
de lá. Idempotente e reversível, como as outras cargas: renomeia só se o nome
antigo ainda existir, e não faz nada se alguém já tiver editado no Admin.
"""

from django.db import migrations

TIPO = "Contrato entre o Fundo e o Cessionário"
ANTES = "Contrato de cessão — modelo base"
DEPOIS = "Contrato de cessão (modelo base)"


def _renomear(apps, de: str, para: str) -> None:
    SubtipoDocumento = apps.get_model("documentos", "SubtipoDocumento")
    SubtipoDocumento.objects.filter(tipo_documento__nome=TIPO, nome=de).update(nome=para)


def aplicar(apps, schema_editor):
    _renomear(apps, ANTES, DEPOIS)


def desfazer(apps, schema_editor):
    _renomear(apps, DEPOIS, ANTES)


class Migration(migrations.Migration):
    dependencies = [("documentos", "0009_subtipos_do_contrato")]

    operations = [migrations.RunPython(aplicar, desfazer)]
