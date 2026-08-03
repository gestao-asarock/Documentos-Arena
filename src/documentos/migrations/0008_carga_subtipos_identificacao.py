"""
Subtipos de documento de identificação e ajuste das regras de envio.

A identificação não pede data de emissão: a emissão do RG não define validade
alguma. CNH e passaporte têm validade própria, tratada pelo subtipo.
"""

from django.db import migrations

#: (nome, tem_validade_propria)
SUBTIPOS_IDENTIFICACAO = [
    ("RG", False),
    # Substitui o RG desde 2023 e já é o documento portado por boa parte das pessoas.
    ("CIN — Carteira de Identidade Nacional", False),
    ("CNH", True),
    ("Passaporte", True),
    ("RNE / CRNM", True),
]

TIPOS_DE_IDENTIFICACAO = [
    "Documento de identificação (RG, CPF e/ou CNH)",
    "Documento de identificação dos representantes (RG, CPF e/ou CNH)",
]


def carregar(apps, schema_editor):
    TipoDocumento = apps.get_model("documentos", "TipoDocumento")
    SubtipoDocumento = apps.get_model("documentos", "SubtipoDocumento")

    for nome_tipo in TIPOS_DE_IDENTIFICACAO:
        tipo = TipoDocumento.objects.filter(nome=nome_tipo).first()
        if tipo is None:
            continue

        tipo.exige_data_emissao = False
        tipo.save()

        for nome, tem_validade in SUBTIPOS_IDENTIFICACAO:
            SubtipoDocumento.objects.update_or_create(
                tipo_documento=tipo,
                nome=nome,
                defaults={"tem_validade_propria": tem_validade},
            )


def remover(apps, schema_editor):
    SubtipoDocumento = apps.get_model("documentos", "SubtipoDocumento")
    SubtipoDocumento.objects.filter(tipo_documento__nome__in=TIPOS_DE_IDENTIFICACAO).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("documentos", "0007_subtipo_e_regras_de_envio"),
    ]

    operations = [
        migrations.RunPython(carregar, remover),
    ]
