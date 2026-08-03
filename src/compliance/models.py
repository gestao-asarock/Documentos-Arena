"""
Parecer de due diligence (AGENTS.md §4.7).

No MVP a análise é **manual** (D22): o analista consulta as fontes, registra o que
encontrou bloco a bloco, anexa evidências e conclui com um veredito de risco. A
integração com a Trillia entra depois, preenchendo os mesmos campos.

Campos separados por bloco, não um texto único: assim o parecer vira dado
auditável e comparável entre contrapartes.
"""

from django.db import models

from contrapartes.models import Habilitacao


class Veredito(models.TextChoices):
    """Classificação por risco — a abordagem baseada em risco da CVM/GAFI."""

    BAIXO = "baixo", "Risco baixo"
    MODERADO = "moderado", "Risco moderado"
    ALTO = "alto", "Risco alto"


class StatusParecer(models.TextChoices):
    RASCUNHO = "rascunho", "Em elaboração"
    CONCLUIDO = "concluido", "Concluído"


class BlocoParecer(models.TextChoices):
    """Os blocos de verificação, na ordem em que aparecem na tela."""

    SITUACAO_CADASTRAL = "situacao_cadastral", "Situação cadastral"
    PROCESSOS = "processos", "Processos judiciais e administrativos"
    SANCOES = "sancoes", "Sanções e listas restritivas"
    PEP = "pep", "Pessoa exposta politicamente (PEP)"
    BLOQUEIOS = "bloqueios", "Bloqueios e restrições"
    MIDIA_ADVERSA = "midia_adversa", "Mídia adversa (webcheck)"
    BENEFICIARIO_FINAL = "beneficiario_final", "Beneficiário final e grupo econômico"
    SOCIOS = "socios", "Sócios e administradores"
    PARTE_RELACIONADA = "parte_relacionada", "Parte relacionada e conflito de interesse"


class ParecerCompliance(models.Model):
    habilitacao = models.OneToOneField(
        Habilitacao, on_delete=models.CASCADE, related_name="parecer_compliance"
    )
    status = models.CharField(
        max_length=16, choices=StatusParecer.choices, default=StatusParecer.RASCUNHO
    )

    # --- Blocos de verificação (§4.7) ---
    situacao_cadastral = models.TextField(
        "situação cadastral",
        blank=True,
        help_text="CPF regular / CNPJ ativo. Para PJ, se o CNAE é compatível com o contratado.",
    )
    processos = models.TextField(
        blank=True,
        help_text="Cível, criminal, trabalhista, fiscal e execuções — separe por esfera.",
    )
    sancoes = models.TextField(
        "sanções e listas restritivas",
        blank=True,
        help_text="ONU, OFAC, União Europeia; CEIS, CNEP, CEPIM, inidôneos do TCU, "
        "lista suja do trabalho escravo, CADIN.",
    )
    pep = models.TextField(
        "PEP",
        blank=True,
        help_text="Titular, sócios, administradores, beneficiário final e "
        "familiares/relacionados próximos.",
    )
    bloqueios = models.TextField(
        "bloqueios e restrições",
        blank=True,
        help_text="Indisponibilidade de bens, restrições cadastrais.",
    )
    midia_adversa = models.TextField(
        "mídia adversa",
        blank=True,
        help_text="O que foi encontrado na busca por notícias negativas.",
    )
    termos_pesquisados = models.CharField(
        max_length=255,
        blank=True,
        help_text="Palavras-chave usadas no webcheck — registre para o parecer ser refazível.",
    )
    beneficiario_final = models.TextField(
        "beneficiário final e grupo econômico",
        blank=True,
        help_text="Quem controla de fato, e a que grupo pertence. Só para PJ.",
    )
    socios = models.TextField(
        "sócios e administradores",
        blank=True,
        help_text="As mesmas checagens replicadas nos sócios relevantes. Só para PJ.",
    )
    parte_relacionada = models.TextField(
        "parte relacionada e conflito de interesse",
        blank=True,
        help_text="Vínculo com o Fundo, o Clube ou a gestora.",
    )

    # --- Conclusão ---
    veredito = models.CharField(
        max_length=16, choices=Veredito.choices, blank=True, help_text="Obrigatório para concluir."
    )
    justificativa = models.TextField(
        blank=True, help_text="Por que este veredito. Obrigatório para concluir."
    )
    comunicado_ao_coaf = models.BooleanField(
        "comunicado ao COAF/UIF",
        default=False,
        help_text="O sistema não comunica: marque se a comunicação foi feita fora daqui. "
        "O prazo legal é de 24 horas a partir da identificação.",
    )
    data_comunicacao_coaf = models.DateField(null=True, blank=True)

    analista = models.ForeignKey("contas.Usuario", on_delete=models.PROTECT, null=True, blank=True)
    data_criacao = models.DateTimeField(auto_now_add=True)
    data_conclusao = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "parecer de compliance"
        verbose_name_plural = "pareceres de compliance"
        ordering = ("-data_criacao",)

    def __str__(self) -> str:
        return f"Parecer — {self.habilitacao.contraparte.nome}"

    @property
    def esta_concluido(self) -> bool:
        return self.status == StatusParecer.CONCLUIDO

    @property
    def eh_risco_alto(self) -> bool:
        return self.veredito == Veredito.ALTO

    def blocos_preenchidos(self) -> list[tuple[str, str]]:
        """Blocos com conteúdo, para exibição em leitura."""
        return [
            (BlocoParecer(campo).label, getattr(self, campo))
            for campo in BlocoParecer.values
            if getattr(self, campo, "")
        ]

    def blocos_em_branco(self) -> list[str]:
        """Blocos ainda não preenchidos — aviso, não impedimento.

        Nem todo bloco se aplica a toda contraparte: sócios e beneficiário final
        não fazem sentido para pessoa física.
        """
        return [
            BlocoParecer(campo).label
            for campo in BlocoParecer.values
            if not getattr(self, campo, "")
        ]


class EvidenciaParecer(models.Model):
    """Print ou documento que sustenta o que foi registrado num bloco."""

    parecer = models.ForeignKey(
        ParecerCompliance, on_delete=models.CASCADE, related_name="evidencias"
    )
    bloco = models.CharField(max_length=32, choices=BlocoParecer.choices)
    arquivo = models.FileField(upload_to="compliance/%Y/%m/")
    nome_original = models.CharField(max_length=255, blank=True)
    descricao = models.CharField("descrição", max_length=255, blank=True)
    data_envio = models.DateTimeField(auto_now_add=True)
    enviada_por = models.ForeignKey(
        "contas.Usuario", on_delete=models.PROTECT, null=True, blank=True
    )

    class Meta:
        verbose_name = "evidência do parecer"
        verbose_name_plural = "evidências do parecer"
        ordering = ("bloco", "data_envio")

    def __str__(self) -> str:
        return f"{self.get_bloco_display()} — {self.nome_original or self.arquivo.name}"
