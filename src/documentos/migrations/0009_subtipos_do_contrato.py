"""
O "Contrato entre o Fundo e o Cessionário" circula em duas peças.

O **contrato-mãe** é modelo base, igual em todas as operações do tipo — não tem
dado de cliente, remete tudo a `[QUALIFICAÇÃO DA PARTE PREVISTA NO TERMO DE
ADESÃO]`. O **Termo de Adesão** é o que muda: nome, CPF, RG, endereço, data,
horário e valor. A análise jurídica do piloto recai sobre o termo.

Mantemos o nome do tipo como está no guia e distinguimos pelo subtipo.
"""

from django.db import migrations

TIPO = "Contrato entre o Fundo e o Cessionário"

SUBTIPOS = [
    ("Termo de Adesão (preenchido)", False),
    ("Contrato de cessão — modelo base", False),
]


def carregar(apps, schema_editor):
    TipoDocumento = apps.get_model("documentos", "TipoDocumento")
    SubtipoDocumento = apps.get_model("documentos", "SubtipoDocumento")

    tipo = TipoDocumento.objects.filter(nome=TIPO).first()
    if tipo is None:
        return

    for nome, tem_validade in SUBTIPOS:
        SubtipoDocumento.objects.update_or_create(
            tipo_documento=tipo, nome=nome, defaults={"tem_validade_propria": tem_validade}
        )


def remover(apps, schema_editor):
    SubtipoDocumento = apps.get_model("documentos", "SubtipoDocumento")
    SubtipoDocumento.objects.filter(tipo_documento__nome=TIPO).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("documentos", "0008_carga_subtipos_identificacao"),
    ]

    operations = [
        migrations.RunPython(carregar, remover),
    ]
