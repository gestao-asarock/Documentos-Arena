"""
O parecer de crédito pode nascer sem enquadramento (AGENTS.md D30).

Parecer do perfil = análise da pessoa, sem contrato. O primeiro contrato que o
usar ancora nele o próprio enquadramento.
"""

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("credito", "0002_parecer_por_enquadramento"),
    ]

    operations = [
        migrations.AlterField(
            model_name="parecercredito",
            name="regra",
            field=models.ForeignKey(
                blank=True,
                help_text=(
                    "Em branco enquanto o parecer é do perfil, sem contrato associado. "
                    "O primeiro contrato que o usar ancora o parecer no seu enquadramento."
                ),
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="pareceres_credito",
                to="operacoes.regraenquadramento",
                verbose_name="enquadramento",
            ),
        ),
    ]
