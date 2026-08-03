from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("documentos", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="tipodocumento",
            name="obrigatorio_no_kit",
            field=models.BooleanField(
                default=True,
                help_text=(
                    "Desmarque para itens condicionais, como a procuração, exigida "
                    "apenas 'quando houver' — não contam como pendência do dossiê."
                ),
                verbose_name="obrigatório no kit",
            ),
        ),
    ]
