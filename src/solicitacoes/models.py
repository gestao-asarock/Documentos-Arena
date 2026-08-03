"""
Solicitação: o formulário que o Clube preenche (AGENTS.md §4.0, Fase 1).

É a porta de entrada de tudo. A partir dela o sistema deduz PF ou PJ, cria ou
reaproveita a contraparte e monta a lista de documentos exigidos.
"""

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone

from contrapartes.models import Contraparte, Habilitacao
from operacoes.models import TipoOperacao


class StatusSolicitacao(models.TextChoices):
    RASCUNHO = "rascunho", "Rascunho"
    EM_HABILITACAO = "em_habilitacao", "Perfil em validação"
    PRONTA_PARA_CONTRATO = "pronta_para_contrato", "Perfil validado"
    CANCELADA = "cancelada", "Cancelado"


class Solicitacao(models.Model):
    """Cadastro de perfil de uma contraparte (AGENTS.md D29).

    Reúne apenas o que é **da pessoa**: identificação, contato e endereço. Nada
    de evento, data ou valor — esses pertencem ao contrato, e é isso que permite
    o mesmo perfil servir a vários contratos.
    """

    contraparte = models.ForeignKey(
        Contraparte, on_delete=models.PROTECT, related_name="solicitacoes"
    )
    habilitacao = models.ForeignKey(
        Habilitacao,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="solicitacoes",
    )

    status = models.CharField(
        max_length=32, choices=StatusSolicitacao.choices, default=StatusSolicitacao.RASCUNHO
    )
    criada_por = models.ForeignKey("contas.Usuario", on_delete=models.PROTECT)
    motivo_cancelamento = models.TextField("motivo do cancelamento", blank=True)
    cancelada_por = models.ForeignKey(
        "contas.Usuario",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="solicitacoes_canceladas",
    )
    data_cancelamento = models.DateTimeField(null=True, blank=True)
    data_criacao = models.DateTimeField(auto_now_add=True)
    data_atualizacao = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "solicitação"
        verbose_name_plural = "solicitações"
        ordering = ("-data_criacao",)

    def __str__(self) -> str:
        return f"Perfil #{self.pk} — {self.contraparte.nome}"

    def pendencias_cadastrais(self):
        """Documentos base que faltam. Sem valor: o kit do perfil não depende de operação."""
        return self.contraparte.pendencias_cadastrais()

    def exigencias_cadastrais(self):
        return self.contraparte.exigencias_cadastrais()

    @property
    def kit_completo(self) -> bool:
        return self.contraparte.kit_completo()

    @property
    def esta_cancelada(self) -> bool:
        return self.status == StatusSolicitacao.CANCELADA

    @property
    def pode_ser_cancelada(self) -> bool:
        """Solicitação com contrato aberto não se cancela: cancele o contrato antes."""
        if self.esta_cancelada:
            return False
        return not self.operacoes.exclude(status="cancelada").exists()

    def cancelar(self, motivo: str, *, usuario=None) -> None:
        """Desiste do pedido. O registro fica, com motivo e autor.

        A habilitação da contraparte **não** é desfeita: ela pertence à
        contraparte e serve a outros pedidos (AGENTS.md D19).
        """
        if self.esta_cancelada:
            raise ValidationError("Esta solicitação já foi cancelada.")
        if self.operacoes.exclude(status="cancelada").exists():
            raise ValidationError(
                "Existe contrato aberto para esta solicitação. Cancele o contrato primeiro."
            )
        if not motivo.strip():
            raise ValidationError({"motivo_cancelamento": "Informe o motivo do cancelamento."})

        self.status = StatusSolicitacao.CANCELADA
        self.motivo_cancelamento = motivo
        self.cancelada_por = usuario
        self.data_cancelamento = timezone.now()
