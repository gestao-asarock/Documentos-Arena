"""
Carga do fluxo piloto: Aluguel de Espaço — Evento até R$ 5.000,00.

A matriz de alçadas do guia tem onze linhas; apenas esta é criada com
`implementada=True`. As demais entram uma a uma, após validação (AGENTS.md D11).
"""

from decimal import Decimal

from django.db import migrations

TIPO_OPERACAO = "Aluguel de Espaço"
CRITERIO = "Evento até R$ 5.000,00"
DOCUMENTO_EXIGIDO = "Contrato entre o Fundo e o Cessionário"


def carregar(apps, schema_editor):
    TipoOperacao = apps.get_model("operacoes", "TipoOperacao")
    RegraEnquadramento = apps.get_model("operacoes", "RegraEnquadramento")
    ExigenciaDocumental = apps.get_model("operacoes", "ExigenciaDocumental")
    TipoDocumento = apps.get_model("documentos", "TipoDocumento")

    tipo, _ = TipoOperacao.objects.update_or_create(
        nome=TIPO_OPERACAO,
        defaults={"descricao": "Cessão de espaço da Neo Química Arena a terceiros."},
    )

    regra, _ = RegraEnquadramento.objects.update_or_create(
        tipo_operacao=tipo,
        criterio=CRITERIO,
        defaults={
            "valor_minimo": Decimal("0.01"),
            "valor_maximo": Decimal("5000.00"),
            # Todas as seis colunas da matriz são obrigatórias neste enquadramento.
            "exige_triagem": True,
            "exige_due_diligence": True,
            "exige_risco_credito": True,
            "exige_juridico": True,
            "exige_assinaturas": True,
            "exige_boletagem": True,
            "waiver": False,
            "implementada": True,
            "ativa": True,
        },
    )

    # Kit Cadastral PJ + contrato: o kit é exigido da contraparte, não da operação.
    documento = TipoDocumento.objects.filter(nome=DOCUMENTO_EXIGIDO).first()
    if documento:
        ExigenciaDocumental.objects.update_or_create(
            regra=regra, tipo_documento=documento, defaults={"obrigatorio": True}
        )


def remover(apps, schema_editor):
    RegraEnquadramento = apps.get_model("operacoes", "RegraEnquadramento")
    RegraEnquadramento.objects.filter(
        tipo_operacao__nome=TIPO_OPERACAO, criterio=CRITERIO
    ).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("operacoes", "0001_initial"),
        ("documentos", "0003_carga_tipos_documento"),
    ]

    operations = [
        migrations.RunPython(carregar, remover),
    ]
