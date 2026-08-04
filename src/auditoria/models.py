"""
Trilha de auditoria (AGENTS.md §6).

Registro de auditoria nunca é editado nem apagado. O Admin expõe apenas leitura.
Nunca grave conteúdo de documento, CPF completo ou token nos detalhes.
"""

from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models


class Acao(models.TextChoices):
    CRIACAO = "criacao", "Criação"
    ENQUADRAMENTO = "enquadramento", "Enquadramento"
    ENVIO_DOCUMENTO = "envio_documento", "Envio de documento"
    EXCLUSAO_DOCUMENTO = "exclusao_documento", "Exclusão de documento"
    ALTERACAO_CADASTRAL = "alteracao_cadastral", "Alteração cadastral"
    ANALISE_IA = "analise_ia", "Análise por IA"
    CONSULTA_COMPLIANCE = "consulta_compliance", "Consulta de compliance"
    TRANSICAO_ESTADO = "transicao_estado", "Transição de estado"
    APROVACAO = "aprovacao", "Aprovação"
    REPROVACAO = "reprovacao", "Reprovação"
    DISPENSA = "dispensa", "Dispensa (waiver)"
    DOWNLOAD = "download", "Download de documento"


class EventoAuditoria(models.Model):
    data_hora = models.DateTimeField(auto_now_add=True, db_index=True)
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        verbose_name="usuário",
        help_text="Nulo quando a ação foi executada pelo sistema (tarefa assíncrona).",
    )
    acao = models.CharField("ação", max_length=32, choices=Acao.choices)
    descricao = models.CharField("descrição", max_length=255)
    endereco_ip = models.GenericIPAddressField("endereço IP", null=True, blank=True)

    # Objeto afetado, qualquer que seja o modelo.
    content_type = models.ForeignKey(ContentType, on_delete=models.PROTECT, null=True)
    object_id = models.PositiveBigIntegerField(null=True)
    objeto = GenericForeignKey("content_type", "object_id")

    class Meta:
        verbose_name = "evento de auditoria"
        verbose_name_plural = "eventos de auditoria"
        ordering = ("-data_hora",)
        indexes = [models.Index(fields=("content_type", "object_id"))]

    def __str__(self) -> str:
        return f"{self.get_acao_display()}: {self.descricao}"
