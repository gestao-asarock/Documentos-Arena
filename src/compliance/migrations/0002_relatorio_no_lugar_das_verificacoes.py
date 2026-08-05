"""
A due diligence deixa de ser digitada bloco a bloco e passa a ser o relatório.

O analista já produz o relatório fora daqui; redigitá-lo em nove campos não
acrescentava nada e alongava a tela. Ficam o veredito (obrigatório), a
justificativa (agora opcional) e o relatório em PDF, que passa a ser exigido
para concluir.

**Esta migration apaga colunas com texto.** Reverter recria os campos vazios: o
conteúdo dos blocos não volta. Antes de aplicar em ambiente com dado real, faça
backup (checklist de deploy, item 4).
"""

import django.db.models.deletion
from django.db import migrations, models

CAMPOS_REMOVIDOS = [
    "situacao_cadastral",
    "processos",
    "sancoes",
    "pep",
    "bloqueios",
    "midia_adversa",
    "termos_pesquisados",
    "beneficiario_final",
    "socios",
    "parte_relacionada",
]


class Migration(migrations.Migration):
    dependencies = [("compliance", "0001_initial")]

    operations = [
        *[
            migrations.RemoveField(model_name="parecercompliance", name=campo)
            for campo in CAMPOS_REMOVIDOS
        ],
        migrations.AlterField(
            model_name="parecercompliance",
            name="justificativa",
            field=models.TextField(
                blank=True, help_text="Opcional: o relatório anexado já sustenta o veredito."
            ),
        ),
        migrations.RenameModel(old_name="EvidenciaParecer", new_name="RelatorioParecer"),
        migrations.RemoveField(model_name="relatorioparecer", name="bloco"),
        migrations.AlterField(
            model_name="relatorioparecer",
            name="parecer",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="relatorios",
                to="compliance.parecercompliance",
            ),
        ),
        migrations.AlterModelOptions(
            name="relatorioparecer",
            options={
                "ordering": ("data_envio",),
                "verbose_name": "relatório do parecer",
                "verbose_name_plural": "relatórios do parecer",
            },
        ),
    ]
