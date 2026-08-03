import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("contrapartes", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="contraparte",
            name="data_nascimento",
            field=models.DateField(blank=True, null=True, verbose_name="data de nascimento"),
        ),
        migrations.AddField(
            model_name="contraparte",
            name="rg",
            field=models.CharField(blank=True, max_length=20, verbose_name="RG"),
        ),
        migrations.AddField(
            model_name="contraparte",
            name="endereco",
            field=models.CharField(blank=True, max_length=255, verbose_name="endereço"),
        ),
        migrations.AlterField(
            model_name="contraparte",
            name="tipo_pessoa",
            field=models.CharField(
                choices=[("pf", "Pessoa física"), ("pj", "Pessoa jurídica")],
                help_text="Preenchido automaticamente a partir do CPF/CNPJ.",
                max_length=2,
                verbose_name="tipo de pessoa",
            ),
        ),
        migrations.AlterField(
            model_name="contraparte",
            name="nome",
            field=models.CharField(help_text="Razão social, no caso de PJ.", max_length=200),
        ),
        migrations.CreateModel(
            name="Habilitacao",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("aguardando_documentos", "Aguardando documentos"),
                            ("em_analise_documental", "Em análise documental"),
                            ("com_pendencia", "Com pendência"),
                            ("em_compliance", "Em análise de compliance"),
                            ("em_credito", "Em análise de crédito"),
                            ("habilitada", "Habilitada"),
                            ("recusada", "Recusada"),
                        ],
                        default="aguardando_documentos",
                        max_length=32,
                    ),
                ),
                (
                    "exige_credito",
                    models.BooleanField(
                        default=False,
                        help_text="Definido pelo enquadramento da solicitação (AGENTS.md §4.4).",
                        verbose_name="exige análise de crédito",
                    ),
                ),
                (
                    "data_conclusao",
                    models.DateTimeField(blank=True, null=True, verbose_name="data da conclusão"),
                ),
                (
                    "data_validade",
                    models.DateField(
                        blank=True,
                        help_text=(
                            "Prazo a definir com o compliance. Em branco, não expira por tempo."
                        ),
                        null=True,
                        verbose_name="válida até",
                    ),
                ),
                ("motivo_recusa", models.TextField(blank=True, verbose_name="motivo da recusa")),
                ("data_criacao", models.DateTimeField(auto_now_add=True)),
                (
                    "contraparte",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="habilitacoes",
                        to="contrapartes.contraparte",
                    ),
                ),
            ],
            options={
                "verbose_name": "habilitação",
                "verbose_name_plural": "habilitações",
                "ordering": ("-data_criacao",),
            },
        ),
    ]
