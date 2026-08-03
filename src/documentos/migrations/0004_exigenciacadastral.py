from decimal import Decimal

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("documentos", "0003_carga_tipos_documento"),
    ]

    operations = [
        migrations.CreateModel(
            name="ExigenciaCadastral",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                (
                    "tipo_pessoa",
                    models.CharField(
                        choices=[("pf", "Pessoa física"), ("pj", "Pessoa jurídica")],
                        max_length=2,
                        verbose_name="tipo de pessoa",
                    ),
                ),
                (
                    "valor_minimo",
                    models.DecimalField(
                        decimal_places=2,
                        default=Decimal("0.00"),
                        help_text="Inclusivo. Zero significa que vale para qualquer valor.",
                        max_digits=14,
                        verbose_name="valor mínimo",
                    ),
                ),
                (
                    "valor_maximo",
                    models.DecimalField(
                        blank=True,
                        decimal_places=2,
                        help_text="Inclusivo. Em branco, não há limite superior.",
                        max_digits=14,
                        null=True,
                        verbose_name="valor máximo",
                    ),
                ),
                (
                    "obrigatorio",
                    models.BooleanField(
                        default=True,
                        help_text=(
                            "Desmarque para itens condicionais, como a procuração "
                            "('quando houver') — não contam como pendência."
                        ),
                    ),
                ),
                (
                    "grupo_alternativo",
                    models.CharField(
                        blank=True,
                        help_text=(
                            "Documentos com o mesmo grupo se substituem: basta um deles. "
                            "Ex.: holerite OU declaração de IR."
                        ),
                        max_length=50,
                    ),
                ),
                ("ativa", models.BooleanField(default=True)),
                (
                    "tipo_documento",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        to="documentos.tipodocumento",
                    ),
                ),
            ],
            options={
                "verbose_name": "exigência cadastral",
                "verbose_name_plural": "exigências cadastrais",
                "ordering": ("tipo_pessoa", "valor_minimo", "tipo_documento__nome"),
            },
        ),
    ]
