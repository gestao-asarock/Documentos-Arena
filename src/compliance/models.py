"""
Parecer de due diligence (AGENTS.md §4.7).

No MVP a análise é **manual** (D22): o analista consulta as fontes fora daqui,
anexa o **relatório** em PDF e conclui com um veredito de risco. O sistema não
pede que ele redigite o conteúdo do relatório em campos separados: o documento é
a evidência, e o que fica registrado aqui é a decisão humana sobre ele.

Sem relatório anexado não há veredito — é o relatório que sustenta a conclusão.
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


class ParecerCompliance(models.Model):
    habilitacao = models.OneToOneField(
        Habilitacao, on_delete=models.CASCADE, related_name="parecer_compliance"
    )
    status = models.CharField(
        max_length=16, choices=StatusParecer.choices, default=StatusParecer.RASCUNHO
    )

    # --- Conclusão ---
    veredito = models.CharField(
        max_length=16, choices=Veredito.choices, blank=True, help_text="Obrigatório para concluir."
    )
    justificativa = models.TextField(
        blank=True, help_text="Opcional: o relatório anexado já sustenta o veredito."
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
        return f"Parecer: {self.habilitacao.contraparte.nome}"

    @property
    def esta_concluido(self) -> bool:
        return self.status == StatusParecer.CONCLUIDO

    @property
    def eh_risco_alto(self) -> bool:
        return self.veredito == Veredito.ALTO

    @property
    def tem_relatorio(self) -> bool:
        return self.relatorios.exists()


class RelatorioParecer(models.Model):
    """O relatório de due diligence, em PDF. É ele que sustenta o veredito."""

    parecer = models.ForeignKey(
        ParecerCompliance, on_delete=models.CASCADE, related_name="relatorios"
    )
    arquivo = models.FileField(upload_to="compliance/%Y/%m/")
    nome_original = models.CharField(max_length=255, blank=True)
    descricao = models.CharField("descrição", max_length=255, blank=True)
    data_envio = models.DateTimeField(auto_now_add=True)
    enviada_por = models.ForeignKey(
        "contas.Usuario", on_delete=models.PROTECT, null=True, blank=True
    )

    class Meta:
        verbose_name = "relatório do parecer"
        verbose_name_plural = "relatórios do parecer"
        ordering = ("data_envio",)

    def __str__(self) -> str:
        return self.nome_original or self.arquivo.name
