import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

BLOCOS = [
    ("consulta", "Consulta de crédito (Serasa e afins)"),
    ("restricoes", "Restrições, protestos e negativações"),
    ("pendencias", "Pendências financeiras e dívidas"),
    ("capacidade", "Capacidade de pagamento"),
    ("balanco", "Balanço, DRE e faturamento"),
]

VEREDITOS = [("baixo", "Risco baixo"), ("moderado", "Risco moderado"), ("alto", "Risco alto")]


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("contrapartes", "0005_arquivo_com_nome_nao_adivinhavel"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="ParecerCredito",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[("rascunho", "Em elaboração"), ("concluido", "Concluído")],
                        default="rascunho",
                        max_length=16,
                    ),
                ),
                (
                    "consulta",
                    models.TextField(
                        blank=True,
                        help_text="Score e o que a consulta retornou. Registre a fonte e a data.",
                        verbose_name="consulta de crédito",
                    ),
                ),
                (
                    "restricoes",
                    models.TextField(
                        blank=True,
                        help_text="Protestos em cartório, negativações, apontamentos.",
                        verbose_name="restrições, protestos e negativações",
                    ),
                ),
                (
                    "pendencias",
                    models.TextField(
                        blank=True,
                        help_text="Dívidas em aberto, parcelamentos, execuções fiscais.",
                        verbose_name="pendências financeiras",
                    ),
                ),
                (
                    "capacidade",
                    models.TextField(
                        blank=True,
                        help_text="A renda ou o faturamento comporta o valor da operação?",
                        verbose_name="capacidade de pagamento",
                    ),
                ),
                (
                    "balanco",
                    models.TextField(
                        blank=True,
                        help_text=(
                            "Só para PJ, e apenas nos enquadramentos que exigem esses documentos."
                        ),
                        verbose_name="balanço, DRE e faturamento",
                    ),
                ),
                (
                    "veredito",
                    models.CharField(
                        blank=True,
                        choices=VEREDITOS,
                        help_text="Obrigatório para concluir.",
                        max_length=16,
                    ),
                ),
                (
                    "justificativa",
                    models.TextField(
                        blank=True, help_text="Por que este veredito. Obrigatório para concluir."
                    ),
                ),
                (
                    "registrado_em_nome_do_time",
                    models.BooleanField(
                        default=True,
                        help_text=(
                            "No MVP o time de Risco não é usuário do sistema: CRM ou Compliance "
                            "registra o parecer produzido por ele (AGENTS.md D9)."
                        ),
                        verbose_name="registrado em nome do time de Risco",
                    ),
                ),
                ("data_criacao", models.DateTimeField(auto_now_add=True)),
                ("data_conclusao", models.DateTimeField(blank=True, null=True)),
                (
                    "analista",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "habilitacao",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="parecer_credito",
                        to="contrapartes.habilitacao",
                    ),
                ),
            ],
            options={
                "verbose_name": "parecer de crédito",
                "verbose_name_plural": "pareceres de crédito",
                "ordering": ("-data_criacao",),
            },
        ),
        migrations.CreateModel(
            name="EvidenciaCredito",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("bloco", models.CharField(choices=BLOCOS, max_length=32)),
                ("arquivo", models.FileField(upload_to="credito/%Y/%m/")),
                ("nome_original", models.CharField(blank=True, max_length=255)),
                (
                    "descricao",
                    models.CharField(blank=True, max_length=255, verbose_name="descrição"),
                ),
                ("data_envio", models.DateTimeField(auto_now_add=True)),
                (
                    "enviada_por",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "parecer",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="evidencias",
                        to="credito.parecercredito",
                    ),
                ),
            ],
            options={
                "verbose_name": "evidência do parecer de crédito",
                "verbose_name_plural": "evidências do parecer de crédito",
                "ordering": ("bloco", "data_envio"),
            },
        ),
    ]
