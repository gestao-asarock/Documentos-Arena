"""
Carga inicial do catálogo de tipos de documento.

Origem: *Guia de Regras de Compliance — FII ARENA v2.0*, página 2. Não invente
tipos: o que não está no guia não entra aqui (AGENTS.md §10).
"""

from django.db import migrations

#: Kit Cadastral PJ — documentação base de toda contraparte pessoa jurídica.
#: (nome, dias_validade, obrigatorio_no_kit)
KIT_CADASTRAL_PJ = [
    ("Contrato Social / Última Alteração Contratual", None, True),
    ("Certidão de Inteiro Teor ou Simplificada — JUCESP", None, True),
    # "quando houver": condicional, não conta como pendência do dossiê.
    ("Procuração", None, False),
    # Único prazo explícito no guia: "até 90 dias após o vencimento".
    ("Comprovante de endereço", 90, True),
    ("Documento de identificação dos representantes (RG, CPF e/ou CNH)", None, True),
]

#: Documentos de operação usados pelo fluxo piloto (AGENTS.md §4.3).
#: Os demais entram junto com seus enquadramentos, um por vez.
DOCUMENTOS_OPERACIONAIS = [
    "Contrato entre o Fundo e o Cessionário",
]


def carregar(apps, schema_editor):
    TipoDocumento = apps.get_model("documentos", "TipoDocumento")

    for nome, dias_validade, obrigatorio in KIT_CADASTRAL_PJ:
        TipoDocumento.objects.update_or_create(
            nome=nome,
            defaults={
                "escopo": "cadastral",
                "kit_cadastral_pj": True,
                "obrigatorio_no_kit": obrigatorio,
                "dias_validade": dias_validade,
            },
        )

    for nome in DOCUMENTOS_OPERACIONAIS:
        TipoDocumento.objects.update_or_create(
            nome=nome,
            defaults={
                "escopo": "operacional",
                "kit_cadastral_pj": False,
                "obrigatorio_no_kit": True,
            },
        )


def remover(apps, schema_editor):
    TipoDocumento = apps.get_model("documentos", "TipoDocumento")
    nomes = [nome for nome, _, _ in KIT_CADASTRAL_PJ] + DOCUMENTOS_OPERACIONAIS
    TipoDocumento.objects.filter(nome__in=nomes).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("documentos", "0002_tipodocumento_obrigatorio_no_kit"),
    ]

    operations = [
        migrations.RunPython(carregar, remover),
    ]
