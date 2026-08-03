from decimal import Decimal

import django.core.validators
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("contrapartes", "0002_habilitacao_e_dados_cadastrais"),
        ("operacoes", "0002_carga_enquadramento_piloto"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Solicitacao",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                (
                    "descricao",
                    models.CharField(
                        help_text=(
                            "Ex.: formatura de balé, ensaio fotográfico, manutenção elétrica."
                        ),
                        max_length=255,
                        verbose_name="descrição do evento ou serviço",
                    ),
                ),
                (
                    "data_evento",
                    models.DateField(blank=True, null=True, verbose_name="data do evento"),
                ),
                (
                    "horario_evento",
                    models.TimeField(blank=True, null=True, verbose_name="horário"),
                ),
                (
                    "valor",
                    models.DecimalField(
                        decimal_places=2,
                        help_text="Define as exigências cadastrais e o enquadramento.",
                        max_digits=14,
                        validators=[django.core.validators.MinValueValidator(Decimal("0.01"))],
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("rascunho", "Rascunho"),
                            ("em_habilitacao", "Em habilitação da contraparte"),
                            ("pronta_para_contrato", "Pronta para contrato"),
                            ("cancelada", "Cancelada"),
                        ],
                        default="rascunho",
                        max_length=32,
                    ),
                ),
                ("data_criacao", models.DateTimeField(auto_now_add=True)),
                ("data_atualizacao", models.DateTimeField(auto_now=True)),
                (
                    "contraparte",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="solicitacoes",
                        to="contrapartes.contraparte",
                    ),
                ),
                (
                    "habilitacao",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="solicitacoes",
                        to="contrapartes.habilitacao",
                    ),
                ),
                (
                    "tipo_operacao",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        to="operacoes.tipooperacao",
                    ),
                ),
                (
                    "criada_por",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "solicitação",
                "verbose_name_plural": "solicitações",
                "ordering": ("-data_criacao",),
            },
        ),
    ]
