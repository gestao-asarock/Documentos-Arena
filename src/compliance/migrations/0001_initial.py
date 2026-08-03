import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

BLOCOS = [
    ("situacao_cadastral", "Situação cadastral"),
    ("processos", "Processos judiciais e administrativos"),
    ("sancoes", "Sanções e listas restritivas"),
    ("pep", "Pessoa exposta politicamente (PEP)"),
    ("bloqueios", "Bloqueios e restrições"),
    ("midia_adversa", "Mídia adversa (webcheck)"),
    ("beneficiario_final", "Beneficiário final e grupo econômico"),
    ("socios", "Sócios e administradores"),
    ("parte_relacionada", "Parte relacionada e conflito de interesse"),
]


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("contrapartes", "0005_arquivo_com_nome_nao_adivinhavel"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="ParecerCompliance",
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
                    "situacao_cadastral",
                    models.TextField(
                        blank=True,
                        help_text=(
                            "CPF regular / CNPJ ativo. Para PJ, se o CNAE é compatível com "
                            "o contratado."
                        ),
                        verbose_name="situação cadastral",
                    ),
                ),
                (
                    "processos",
                    models.TextField(
                        blank=True,
                        help_text=(
                            "Cível, criminal, trabalhista, fiscal e execuções — separe por esfera."
                        ),
                    ),
                ),
                (
                    "sancoes",
                    models.TextField(
                        blank=True,
                        help_text=(
                            "ONU, OFAC, União Europeia; CEIS, CNEP, CEPIM, inidôneos do TCU, "
                            "lista suja do trabalho escravo, CADIN."
                        ),
                        verbose_name="sanções e listas restritivas",
                    ),
                ),
                (
                    "pep",
                    models.TextField(
                        blank=True,
                        help_text=(
                            "Titular, sócios, administradores, beneficiário final e "
                            "familiares/relacionados próximos."
                        ),
                        verbose_name="PEP",
                    ),
                ),
                (
                    "bloqueios",
                    models.TextField(
                        blank=True,
                        help_text="Indisponibilidade de bens, restrições cadastrais.",
                        verbose_name="bloqueios e restrições",
                    ),
                ),
                (
                    "midia_adversa",
                    models.TextField(
                        blank=True,
                        help_text="O que foi encontrado na busca por notícias negativas.",
                        verbose_name="mídia adversa",
                    ),
                ),
                (
                    "termos_pesquisados",
                    models.CharField(
                        blank=True,
                        help_text=(
                            "Palavras-chave usadas no webcheck — registre para o parecer "
                            "ser refazível."
                        ),
                        max_length=255,
                    ),
                ),
                (
                    "beneficiario_final",
                    models.TextField(
                        blank=True,
                        help_text="Quem controla de fato, e a que grupo pertence. Só para PJ.",
                        verbose_name="beneficiário final e grupo econômico",
                    ),
                ),
                (
                    "socios",
                    models.TextField(
                        blank=True,
                        help_text=(
                            "As mesmas checagens replicadas nos sócios relevantes. Só para PJ."
                        ),
                        verbose_name="sócios e administradores",
                    ),
                ),
                (
                    "parte_relacionada",
                    models.TextField(
                        blank=True,
                        help_text="Vínculo com o Fundo, o Clube ou a gestora.",
                        verbose_name="parte relacionada e conflito de interesse",
                    ),
                ),
                (
                    "veredito",
                    models.CharField(
                        blank=True,
                        choices=[
                            ("baixo", "Risco baixo"),
                            ("moderado", "Risco moderado"),
                            ("alto", "Risco alto"),
                        ],
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
                    "comunicado_ao_coaf",
                    models.BooleanField(
                        default=False,
                        help_text=(
                            "O sistema não comunica: marque se a comunicação foi feita fora "
                            "daqui. O prazo legal é de 24 horas a partir da identificação."
                        ),
                        verbose_name="comunicado ao COAF/UIF",
                    ),
                ),
                ("data_comunicacao_coaf", models.DateField(blank=True, null=True)),
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
                        related_name="parecer_compliance",
                        to="contrapartes.habilitacao",
                    ),
                ),
            ],
            options={
                "verbose_name": "parecer de compliance",
                "verbose_name_plural": "pareceres de compliance",
                "ordering": ("-data_criacao",),
            },
        ),
        migrations.CreateModel(
            name="EvidenciaParecer",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("bloco", models.CharField(choices=BLOCOS, max_length=32)),
                ("arquivo", models.FileField(upload_to="compliance/%Y/%m/")),
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
                        to="compliance.parecercompliance",
                    ),
                ),
            ],
            options={
                "verbose_name": "evidência do parecer",
                "verbose_name_plural": "evidências do parecer",
                "ordering": ("bloco", "data_envio"),
            },
        ),
    ]
