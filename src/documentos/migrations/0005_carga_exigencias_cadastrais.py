"""
Kit cadastral por tipo de pessoa (AGENTS.md §4.5).

PJ vem do guia, página 2. PF vem de definição do responsável, incluindo a
comprovação de renda acima de R$ 4.000,00 (D20).
"""

from decimal import Decimal

from django.db import migrations

DOCUMENTOS_PF = [
    ("Documento de identificação (RG, CPF e/ou CNH)", None),
    ("Comprovante de residência", 90),
    ("Holerite", None),
    ("Declaração de Imposto de Renda", None),
]

#: (nome do tipo, valor_minimo, obrigatorio, grupo_alternativo)
EXIGENCIAS_PF = [
    ("Documento de identificação (RG, CPF e/ou CNH)", Decimal("0.00"), True, ""),
    ("Comprovante de residência", Decimal("0.00"), True, ""),
    # Acima de R$ 4.000,00: holerite OU declaração de IR — basta um dos dois.
    ("Holerite", Decimal("4000.01"), True, "renda"),
    ("Declaração de Imposto de Renda", Decimal("4000.01"), True, "renda"),
]

EXIGENCIAS_PJ = [
    ("Contrato Social / Última Alteração Contratual", True),
    ("Certidão de Inteiro Teor ou Simplificada — JUCESP", True),
    ("Procuração", False),
    ("Comprovante de endereço", True),
    ("Documento de identificação dos representantes (RG, CPF e/ou CNH)", True),
]


def carregar(apps, schema_editor):
    TipoDocumento = apps.get_model("documentos", "TipoDocumento")
    ExigenciaCadastral = apps.get_model("documentos", "ExigenciaCadastral")

    for nome, dias_validade in DOCUMENTOS_PF:
        TipoDocumento.objects.update_or_create(
            nome=nome,
            defaults={
                "escopo": "cadastral",
                "kit_cadastral_pj": False,
                "obrigatorio_no_kit": True,
                "dias_validade": dias_validade,
            },
        )

    for nome, valor_minimo, obrigatorio, grupo in EXIGENCIAS_PF:
        ExigenciaCadastral.objects.update_or_create(
            tipo_pessoa="pf",
            tipo_documento=TipoDocumento.objects.get(nome=nome),
            defaults={
                "valor_minimo": valor_minimo,
                "obrigatorio": obrigatorio,
                "grupo_alternativo": grupo,
            },
        )

    for nome, obrigatorio in EXIGENCIAS_PJ:
        ExigenciaCadastral.objects.update_or_create(
            tipo_pessoa="pj",
            tipo_documento=TipoDocumento.objects.get(nome=nome),
            defaults={"valor_minimo": Decimal("0.00"), "obrigatorio": obrigatorio},
        )


def remover(apps, schema_editor):
    ExigenciaCadastral = apps.get_model("documentos", "ExigenciaCadastral")
    ExigenciaCadastral.objects.all().delete()


class Migration(migrations.Migration):
    dependencies = [
        ("documentos", "0004_exigenciacadastral"),
    ]

    operations = [
        migrations.RunPython(carregar, remover),
    ]
