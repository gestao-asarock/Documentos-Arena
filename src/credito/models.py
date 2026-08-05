"""
Parecer de risco e crédito — etapa 3 do guia (AGENTS.md §4.8, D9 e D23).

Roda **depois** do compliance e só nos enquadramentos em que a matriz exige. A
análise é manual: a fonte prevista é o Serasa, ainda não confirmada. Sem IA nesta
etapa — no fluxo piloto não existe balanço para analisar (§4.2).

Mesmo desenho do compliance (D50): o analista anexa **o relatório em PDF** e
conclui com o veredito. Sem relatório não há veredito.
"""

from django.db import models
from django.utils import timezone


class Veredito(models.TextChoices):
    BAIXO = "baixo", "Risco baixo"
    MODERADO = "moderado", "Risco moderado"
    ALTO = "alto", "Risco alto"


class StatusParecer(models.TextChoices):
    RASCUNHO = "rascunho", "Em elaboração"
    CONCLUIDO = "concluido", "Concluído"


class ParecerCredito(models.Model):
    """Análise de crédito da contraparte (AGENTS.md D30).

    Nasce na esteira do **perfil**, como avaliação da pessoa — score, restrições,
    protestos —, sem valor de referência. O primeiro contrato que a usar ancora o
    parecer no enquadramento dele; a partir daí, contrato de tipo diferente ou de
    outra faixa exige nova análise, porque um parecer feito para R$ 2.000,00 não
    sustenta R$ 200.000,00.
    """

    contraparte = models.ForeignKey(
        "contrapartes.Contraparte", on_delete=models.CASCADE, related_name="pareceres_credito"
    )
    regra = models.ForeignKey(
        "operacoes.RegraEnquadramento",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="pareceres_credito",
        verbose_name="enquadramento",
        help_text="Em branco enquanto o parecer é do perfil, sem contrato associado. "
        "O primeiro contrato que o usar ancora o parecer no seu enquadramento.",
    )
    operacao = models.ForeignKey(
        "operacoes.Operacao",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="pareceres_credito",
        help_text="Contrato que motivou a análise.",
    )
    status = models.CharField(
        max_length=16, choices=StatusParecer.choices, default=StatusParecer.RASCUNHO
    )

    veredito = models.CharField(
        max_length=16, choices=Veredito.choices, blank=True, help_text="Obrigatório para concluir."
    )
    justificativa = models.TextField(
        blank=True, help_text="Opcional: o relatório anexado já sustenta o veredito."
    )

    analista = models.ForeignKey("contas.Usuario", on_delete=models.PROTECT, null=True, blank=True)
    registrado_em_nome_do_time = models.BooleanField(
        "registrado em nome do time de Risco",
        default=True,
        help_text="No MVP o time de Risco não é usuário do sistema: CRM ou Compliance "
        "registra o parecer produzido por ele (AGENTS.md D9).",
    )
    data_criacao = models.DateTimeField(auto_now_add=True)
    data_conclusao = models.DateTimeField(null=True, blank=True)
    data_validade = models.DateField(
        "válido até",
        null=True,
        blank=True,
        help_text="Prazo a definir com o compliance. Em branco, não expira por tempo.",
    )

    class Meta:
        verbose_name = "parecer de crédito"
        verbose_name_plural = "pareceres de crédito"
        ordering = ("-data_criacao",)

    def __str__(self) -> str:
        alcance = self.regra.criterio if self.regra_id else "perfil"
        return f"Crédito: {self.contraparte.nome} ({alcance})"

    @property
    def esta_concluido(self) -> bool:
        return self.status == StatusParecer.CONCLUIDO

    @property
    def esta_vigente(self) -> bool:
        """Concluído e dentro do prazo, quando houver prazo definido."""
        if not self.esta_concluido:
            return False
        return self.data_validade is None or self.data_validade >= timezone.localdate()

    @property
    def tem_relatorio(self) -> bool:
        return self.relatorios.exists()


class RelatorioCredito(models.Model):
    """O relatório da análise de crédito, em PDF. É ele que sustenta o veredito."""

    parecer = models.ForeignKey(ParecerCredito, on_delete=models.CASCADE, related_name="relatorios")
    arquivo = models.FileField(upload_to="credito/%Y/%m/")
    nome_original = models.CharField(max_length=255, blank=True)
    descricao = models.CharField("descrição", max_length=255, blank=True)
    data_envio = models.DateTimeField(auto_now_add=True)
    enviada_por = models.ForeignKey(
        "contas.Usuario", on_delete=models.PROTECT, null=True, blank=True
    )

    class Meta:
        verbose_name = "relatório do parecer de crédito"
        verbose_name_plural = "relatórios do parecer de crédito"
        ordering = ("data_envio",)

    def __str__(self) -> str:
        return self.nome_original or self.arquivo.name
