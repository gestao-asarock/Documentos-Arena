"""
O parecer de crédito passa a valer para o par contraparte + enquadramento
(AGENTS.md D30).

Uma análise feita para R$ 2.000,00 não sustenta R$ 200.000,00 — por isso o
parecer é reaproveitado só no mesmo tipo e na mesma faixa. Os pareceres antigos
(ligados à habilitação) são descartados: eram dados de teste.
"""

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("credito", "0001_initial"),
        ("contrapartes", "0006_perfil_sem_credito"),
        ("operacoes", "0005_contrato_com_evento_e_documentos"),
    ]

    operations = [
        migrations.RunPython(
            lambda apps, schema: apps.get_model("credito", "ParecerCredito").objects.all().delete(),
            migrations.RunPython.noop,
        ),
        migrations.RemoveField(model_name="parecercredito", name="habilitacao"),
        migrations.AddField(
            model_name="parecercredito",
            name="contraparte",
            field=models.ForeignKey(
                default=None,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="pareceres_credito",
                to="contrapartes.contraparte",
            ),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="parecercredito",
            name="regra",
            field=models.ForeignKey(
                default=None,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="pareceres_credito",
                to="operacoes.regraenquadramento",
                verbose_name="enquadramento",
            ),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="parecercredito",
            name="operacao",
            field=models.ForeignKey(
                blank=True,
                help_text="Contrato que motivou a análise.",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="pareceres_credito",
                to="operacoes.operacao",
            ),
        ),
        # Sem registros antigos, os campos podem ser obrigatórios de fato.
        migrations.AlterField(
            model_name="parecercredito",
            name="contraparte",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="pareceres_credito",
                to="contrapartes.contraparte",
            ),
        ),
        migrations.AlterField(
            model_name="parecercredito",
            name="regra",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="pareceres_credito",
                to="operacoes.regraenquadramento",
                verbose_name="enquadramento",
            ),
        ),
        migrations.AddField(
            model_name="parecercredito",
            name="data_validade",
            field=models.DateField(
                blank=True,
                help_text=(
                    "Prazo a definir com o compliance. Em branco, não expira por tempo."
                ),
                null=True,
                verbose_name="válido até",
            ),
        ),
    ]
