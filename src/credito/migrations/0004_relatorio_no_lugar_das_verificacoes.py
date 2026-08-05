"""
O crédito recebe o mesmo desenho do compliance (AGENTS.md D50).

Saem os cinco campos de "Verificações"; a justificativa vira opcional e o
relatório em PDF passa a ser exigido para concluir.

**Esta migration apaga colunas com texto.** Reverter recria os campos vazios: o
conteúdo não volta. Antes de aplicar em ambiente com dado real, faça backup
(checklist de deploy, item 4).
"""

import django.db.models.deletion
from django.db import migrations, models

CAMPOS_REMOVIDOS = ["consulta", "restricoes", "pendencias", "capacidade", "balanco"]


class Migration(migrations.Migration):
    dependencies = [("credito", "0003_parecer_do_perfil")]

    operations = [
        *[
            migrations.RemoveField(model_name="parecercredito", name=campo)
            for campo in CAMPOS_REMOVIDOS
        ],
        migrations.AlterField(
            model_name="parecercredito",
            name="justificativa",
            field=models.TextField(
                blank=True, help_text="Opcional: o relatório anexado já sustenta o veredito."
            ),
        ),
        migrations.RenameModel(old_name="EvidenciaCredito", new_name="RelatorioCredito"),
        migrations.RemoveField(model_name="relatoriocredito", name="bloco"),
        migrations.AlterField(
            model_name="relatoriocredito",
            name="parecer",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="relatorios",
                to="credito.parecercredito",
            ),
        ),
        migrations.AlterModelOptions(
            name="relatoriocredito",
            options={
                "ordering": ("data_envio",),
                "verbose_name": "relatório do parecer de crédito",
                "verbose_name_plural": "relatórios do parecer de crédito",
            },
        ),
    ]
