"""
Alinha os `help_text` que perderam o travessão (AGENTS.md D49).

A limpeza mexeu no modelo e não nas migrations, então `makemigrations` pedia uma
corretiva. Nada aqui gera SQL: `help_text` e `verbose_name` só existem para o
Django. Fica escrita à mão para não arrastar junto qualquer outra diferença.
"""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("documentos", "0010_renomear_subtipo_contrato"),
    ]

    operations = [
        migrations.AlterField(
            model_name="exigenciacadastral",
            name="obrigatorio",
            field=models.BooleanField(
                default=True,
                help_text=(
                    "Desmarque para itens condicionais, como a procuração "
                    "('quando houver'); não contam como pendência."
                ),
            ),
        ),
        migrations.AlterField(
            model_name="tipodocumento",
            name="exige_data_emissao",
            field=models.BooleanField(
                default=True,
                help_text="Desmarque quando a emissão não define a validade, como o RG.",
                verbose_name="exige data de emissão",
            ),
        ),
        migrations.AlterField(
            model_name="tipodocumento",
            name="obrigatorio_no_kit",
            field=models.BooleanField(
                default=True,
                help_text=(
                    "Desmarque para itens condicionais, como a procuração, exigida "
                    "apenas 'quando houver'; não contam como pendência do dossiê."
                ),
                verbose_name="obrigatório no kit",
            ),
        ),
    ]
