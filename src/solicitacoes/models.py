"""
Solicitação: o formulário que o Clube preenche (AGENTS.md §4.0, Fase 1).

É a porta de entrada de tudo. A partir dela o sistema deduz PF ou PJ, cria ou
reaproveita a contraparte e monta a lista de documentos exigidos.
"""

from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from contrapartes.models import Contraparte, Habilitacao

#: Não é status de nada: é o selo cinza de "não se aplica", usado quando o
#: perfil está cancelado e a validação deixou de ter o que dizer. Está no mapa
#: de cores como qualquer status (operacoes/templatetags/situacao.py).
VALIDACAO_NAO_SE_APLICA = "nao_se_aplica"


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
        return f"Perfil #{self.pk}: {self.contraparte.nome}"

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
    def situacao_da_validacao(self) -> dict:
        """Selo da coluna "Validação" — status bruto e rótulo, para o badge.

        Perfil cancelado não tem validação em curso. Mostrar "Aguardando
        documentos" num cadastro encerrado faz parecer que alguém ainda espera
        documento, e é justamente o oposto: dali não sai mais nada. Por isso o
        selo fica cinza, dizendo que não se aplica.
        """
        if self.esta_cancelada:
            return {"status": VALIDACAO_NAO_SE_APLICA, "rotulo": "Cancelada"}
        if self.habilitacao is None:
            return {"status": "", "rotulo": ""}
        return {
            "status": self.habilitacao.status,
            "rotulo": self.habilitacao.get_status_display(),
        }

    @property
    def contratos_em_andamento(self):
        """Contratos da contraparte que ainda não terminaram."""
        return self.contraparte.operacoes.exclude(
            status__in=["cancelada", "concluida", "reprovada", "dispensada"]
        )

    @property
    def pode_ser_editada(self) -> bool:
        """Cadastro validado não se altera (AGENTS.md D47).

        Depois que compliance e crédito concluíram, os dados são a base de uma
        decisão tomada. Mudá-los faria a validação passar a atestar coisa
        diferente da que foi analisada — e o perfil já pode estar sustentando
        contrato. Para corrigir dado de contraparte validada, o caminho é uma
        revalidação explícita, que ainda não existe.
        """
        if self.esta_cancelada:
            return False
        return not self.contraparte.esta_habilitada

    @property
    def pode_ser_cancelada(self) -> bool:
        """Perfil com contrato em andamento não se cancela: encerre o contrato antes."""
        if self.esta_cancelada:
            return False
        return not self.contratos_em_andamento.exists()

    def cancelar(self, motivo: str, *, usuario=None) -> None:
        """Encerra o cadastro do perfil. O registro fica, com motivo e autor."""
        if self.esta_cancelada:
            raise ValidationError("Este perfil já foi cancelado.")
        if self.contratos_em_andamento.exists():
            raise ValidationError(
                "Existe contrato em andamento com esta contraparte. Encerre-o primeiro."
            )
        if not motivo.strip():
            raise ValidationError({"motivo_cancelamento": "Informe o motivo do cancelamento."})

        self.status = StatusSolicitacao.CANCELADA
        self.motivo_cancelamento = motivo
        self.cancelada_por = usuario
        self.data_cancelamento = timezone.now()
