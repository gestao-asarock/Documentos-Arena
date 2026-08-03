"""
Amarra a Fase 2 à Fase 1 (AGENTS.md §4.0).

A operação passa a apontar para a solicitação que a originou, e as etapas
cumpridas na habilitação ganham status próprio — o fluxo aparece inteiro sem
que triagem, due diligence e crédito sejam refeitos a cada contrato.
"""

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("operacoes", "0002_carga_enquadramento_piloto"),
        ("solicitacoes", "0002_alter_solicitacao_id"),
    ]

    operations = [
        migrations.AddField(
            model_name="operacao",
            name="solicitacao",
            field=models.ForeignKey(
                blank=True,
                help_text=(
                    "Pedido que originou o contrato. A Fase 2 nasce da Fase 1 (AGENTS.md §4.0)."
                ),
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="operacoes",
                to="solicitacoes.solicitacao",
            ),
        ),
        migrations.AlterField(
            model_name="etapaaprovacao",
            name="status",
            field=models.CharField(
                choices=[
                    ("pendente", "Pendente"),
                    ("em_analise", "Em análise"),
                    ("aprovada", "Aprovada"),
                    ("reprovada", "Reprovada"),
                    ("dispensada", "Não aplicável"),
                    ("registrada_externamente", "Registrada externamente"),
                    ("cumprida_na_habilitacao", "Cumprida na habilitação"),
                ],
                default="pendente",
                max_length=32,
            ),
        ),
    ]
