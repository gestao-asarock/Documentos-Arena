"""
Operações e a tabela de regras de enquadramento (AGENTS.md §4.4).

O enquadramento é **dado em tabela**, consultado em tempo de execução e editável
no Admin. Nunca escreva `if valor < 5000` em view ou serviço.
"""

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone

from contrapartes.models import Contraparte
from documentos.models import EscopoDocumento, StatusDocumento, TipoDocumento

from .estados import (
    ESTADOS_QUE_NAO_CANCELAM,
    ESTADOS_TERMINAIS,
    ORDEM_ETAPAS,
    PAPEL_RESPONSAVEL,
    TRANSICOES,
    Etapa,
    StatusEtapa,
    StatusOperacao,
    TransicaoInvalida,
)


class TipoOperacao(models.Model):
    """Processo do guia: Aluguel de Espaço, Reembolso, Pagamentos, Serviços NQA, Compras."""

    nome = models.CharField(max_length=120, unique=True)
    descricao = models.TextField("descrição", blank=True)
    ativo = models.BooleanField(default=True)

    class Meta:
        verbose_name = "tipo de operação"
        verbose_name_plural = "tipos de operação"
        ordering = ("nome",)

    def __str__(self) -> str:
        return self.nome


class RegraEnquadramento(models.Model):
    """Uma linha da matriz de alçadas do guia (AGENTS.md §4.4).

    A faixa de valor é **inclusiva nos dois extremos**: `valor_minimo` e
    `valor_maximo` fazem parte da faixa. "Até R$ 5.000,00" é
    `valor_maximo = 5000.00`; "acima de R$ 20.000,00" é `valor_minimo = 20000.01`.
    """

    tipo_operacao = models.ForeignKey(TipoOperacao, on_delete=models.PROTECT, related_name="regras")
    criterio = models.CharField(
        "critério",
        max_length=200,
        help_text='Texto do guia. Ex.: "Evento até R$ 5.000,00".',
    )
    valor_minimo = models.DecimalField(
        "valor mínimo",
        max_digits=14,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0.00"))],
        help_text="Inclusivo.",
    )
    valor_maximo = models.DecimalField(
        "valor máximo",
        max_digits=14,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Inclusivo. Em branco, não há limite superior.",
    )

    # Alçadas — as seis colunas da matriz do guia.
    exige_triagem = models.BooleanField("triagem CRM", default=True)
    exige_due_diligence = models.BooleanField("compliance (DD)", default=False)
    exige_risco_credito = models.BooleanField("risco / crédito", default=False)
    exige_juridico = models.BooleanField("jurídico ASA/Genial", default=False)
    exige_assinaturas = models.BooleanField("assinaturas", default=False)
    exige_boletagem = models.BooleanField("boletagem e liquidação", default=True)

    waiver = models.BooleanField(
        default=False,
        help_text="Dispensa documentação e todas as etapas de aprovação. "
        "Compras até R$ 10.000,00, conforme o guia.",
    )
    implementada = models.BooleanField(
        default=False,
        help_text="Marcada apenas nos enquadramentos liberados para uso. "
        "O MVP roda um por vez (AGENTS.md D11).",
    )
    ativa = models.BooleanField(default=True)

    class Meta:
        verbose_name = "regra de enquadramento"
        verbose_name_plural = "regras de enquadramento"
        ordering = ("tipo_operacao__nome", "valor_minimo")

    def __str__(self) -> str:
        return f"{self.tipo_operacao}: {self.criterio}"

    def clean(self):
        if self.valor_maximo is not None and self.valor_maximo < self.valor_minimo:
            raise ValidationError(
                {"valor_maximo": "O valor máximo não pode ser menor que o mínimo."}
            )

    def cobre(self, valor: Decimal) -> bool:
        """A faixa cobre este valor? Extremos são inclusivos."""
        if valor < self.valor_minimo:
            return False
        return self.valor_maximo is None or valor <= self.valor_maximo

    def etapas_exigidas(self) -> list[str]:
        """Etapas obrigatórias deste enquadramento, na ordem do fluxo."""
        if self.waiver:
            return []

        mapa = {
            Etapa.TRIAGEM: self.exige_triagem,
            Etapa.DUE_DILIGENCE: self.exige_due_diligence,
            Etapa.RISCO_CREDITO: self.exige_risco_credito,
            Etapa.JURIDICO: self.exige_juridico,
            Etapa.ASSINATURAS: self.exige_assinaturas,
            Etapa.ENVIO_NF: self.exige_boletagem,
            Etapa.BOLETAGEM: self.exige_boletagem,
            Etapa.LIQUIDACAO: self.exige_boletagem,
        }
        return [etapa for etapa in ORDEM_ETAPAS if mapa[etapa]]


class ExigenciaDocumental(models.Model):
    """Documento que um enquadramento exige, além do Kit Cadastral."""

    regra = models.ForeignKey(
        RegraEnquadramento, on_delete=models.CASCADE, related_name="exigencias"
    )
    tipo_documento = models.ForeignKey(TipoDocumento, on_delete=models.PROTECT)
    obrigatorio = models.BooleanField(default=True)

    class Meta:
        verbose_name = "exigência documental"
        verbose_name_plural = "exigências documentais"
        unique_together = ("regra", "tipo_documento")

    def __str__(self) -> str:
        return f"{self.tipo_documento} ({self.regra.criterio})"

    def clean(self):
        if self.tipo_documento_id and self.tipo_documento.escopo != EscopoDocumento.OPERACIONAL:
            raise ValidationError(
                {"tipo_documento": "Exigência de operação deve usar tipo de escopo operacional."}
            )


class Operacao(models.Model):
    """Caso concreto a ser aprovado: um aluguel, uma compra, um pagamento."""

    contraparte = models.ForeignKey(Contraparte, on_delete=models.PROTECT, related_name="operacoes")
    tipo_operacao = models.ForeignKey(TipoOperacao, on_delete=models.PROTECT)

    # Dados do evento/serviço: pertencem ao contrato, não ao perfil (AGENTS.md D29).
    data_evento = models.DateField("data do evento", null=True, blank=True)
    horario_evento = models.TimeField("horário", null=True, blank=True)

    #: Documentos do perfil escolhidos para atender às exigências deste contrato.
    #: Ficam no perfil e podem ser reaproveitados em operações futuras.
    documentos = models.ManyToManyField(
        "contrapartes.DocumentoCadastral",
        blank=True,
        related_name="operacoes",
        verbose_name="documentos complementares",
    )
    valor_total = models.DecimalField(
        "valor total",
        max_digits=14,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    descricao = models.TextField("descrição")
    regra = models.ForeignKey(
        RegraEnquadramento,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        verbose_name="enquadramento",
        help_text="Definido no momento do enquadramento; congelado depois disso.",
    )
    status = models.CharField(
        max_length=32, choices=StatusOperacao.choices, default=StatusOperacao.RASCUNHO
    )
    criada_por = models.ForeignKey(
        "contas.Usuario", on_delete=models.PROTECT, related_name="operacoes_criadas"
    )
    motivo_reprovacao = models.TextField("motivo da reprovação", blank=True)
    motivo_cancelamento = models.TextField("motivo do cancelamento", blank=True)
    cancelada_por = models.ForeignKey(
        "contas.Usuario",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="operacoes_canceladas",
    )
    data_cancelamento = models.DateTimeField(null=True, blank=True)
    data_criacao = models.DateTimeField(auto_now_add=True)
    data_atualizacao = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "operação"
        verbose_name_plural = "operações"
        ordering = ("-data_criacao",)

    def __str__(self) -> str:
        return f"#{self.pk} {self.tipo_operacao}: {self.contraparte.nome}"

    # -- Regras de imutabilidade (AGENTS.md §6, D13) -------------------------

    @property
    def esta_em_rascunho(self) -> bool:
        return self.status == StatusOperacao.RASCUNHO

    @property
    def esta_encerrada(self) -> bool:
        return self.status in ESTADOS_TERMINAIS

    def clean(self):
        """Valor e tipo ficam congelados assim que a operação sai de rascunho.

        Reenquadramento de operação em andamento é feature futura: para corrigir,
        cancela-se e abre-se outra (AGENTS.md D13).
        """
        if not self.pk or self.esta_em_rascunho:
            return

        anterior = (
            type(self).objects.filter(pk=self.pk).values("valor_total", "tipo_operacao_id").first()
        )
        if not anterior:
            return
        if anterior["valor_total"] != self.valor_total:
            raise ValidationError(
                {"valor_total": "O valor não pode ser alterado após o início do processo."}
            )
        if anterior["tipo_operacao_id"] != self.tipo_operacao_id:
            raise ValidationError(
                {"tipo_operacao": "O tipo não pode ser alterado após o início do processo."}
            )

    # -- Máquina de estados --------------------------------------------------

    def _transicionar(self, novo_status: str) -> None:
        if novo_status not in TRANSICOES.get(self.status, set()):
            raise TransicaoInvalida(
                f"Não é possível ir de '{self.get_status_display()}' para "
                f"'{StatusOperacao(novo_status).label}'."
            )
        self.status = novo_status

    @property
    def esta_cancelada(self) -> bool:
        """Mesmo nome que em `Solicitacao`: a régua de exclusão serve aos dois."""
        return self.status == StatusOperacao.CANCELADA

    @property
    def pode_ser_cancelada(self) -> bool:
        return self.status not in ESTADOS_QUE_NAO_CANCELAM

    def cancelar(self, motivo: str, *, usuario=None) -> None:
        """Encerra o contrato por decisão de quem o abriu.

        Cancelar não é apagar: o registro fica, com motivo e autor. Depois de
        assinado não se cancela — desfazer contrato assinado é distrato.
        """
        if not self.pode_ser_cancelada:
            raise TransicaoInvalida(
                f"Operação em '{self.get_status_display()}' não pode ser cancelada."
            )
        if not motivo.strip():
            raise ValidationError({"motivo_cancelamento": "Informe o motivo do cancelamento."})

        self.status = StatusOperacao.CANCELADA
        self.motivo_cancelamento = motivo
        self.cancelada_por = usuario
        self.data_cancelamento = timezone.now()

    def reprovar(self, motivo: str) -> None:
        """Reprovação interrompe o fluxo e exige parecer (AGENTS.md §4.7)."""
        if self.esta_encerrada:
            raise TransicaoInvalida("Operação já encerrada não pode ser reprovada.")
        if not motivo.strip():
            raise ValidationError({"motivo_reprovacao": "Informe o motivo da reprovação."})
        self.status = StatusOperacao.REPROVADA
        self.motivo_reprovacao = motivo

    # -- Consultas -----------------------------------------------------------

    @property
    def etapa_atual(self):
        """Primeira etapa ainda não decidida, na ordem do fluxo."""
        pendentes = [
            e
            for e in self.etapas.all()
            if e.status in {StatusEtapa.PENDENTE, StatusEtapa.EM_ANALISE}
        ]
        if not pendentes:
            return None
        return min(pendentes, key=lambda e: ORDEM_ETAPAS.index(Etapa(e.etapa)))

    def documentos_exigidos(self) -> list[TipoDocumento]:
        """Tipos que este contrato exige, além do kit base do perfil.

        Vêm de duas origens: as exigências do enquadramento (contrato, notas,
        cotações) e as exigências cadastrais por faixa de valor — a comprovação
        de renda de PF acima de R$ 4.000,00, por exemplo (AGENTS.md §4.5).
        """
        if not self.regra_id:
            return []

        do_enquadramento = [
            e.tipo_documento for e in self.regra.exigencias.select_related("tipo_documento")
        ]

        # As do perfil já foram entregues; aqui só o que a faixa acrescenta.
        base = {e.tipo_documento_id for e in self.contraparte.exigencias_cadastrais()}
        por_faixa = [
            exigencia.tipo_documento
            for exigencia in self.contraparte.exigencias_cadastrais(self.valor_total)
            if exigencia.tipo_documento_id not in base
        ]

        vistos, exigidos = set(), []
        for tipo in do_enquadramento + por_faixa:
            if tipo.id not in vistos:
                vistos.add(tipo.id)
                exigidos.append(tipo)
        return exigidos

    def documentos_pendentes(self) -> list[TipoDocumento]:
        """Exigências ainda sem documento **aprovado e vigente**.

        Inclui o que já foi enviado e aguarda conferência: enviar não é aprovar
        (AGENTS.md §4.5). Para a tela, use `situacao_documental`, que separa o
        que falta enviar do que está em análise.
        """
        atendidos = {d.tipo_id for d in self.documentos.all() if d.esta_vigente}
        return [tipo for tipo in self.documentos_exigidos() if tipo.id not in atendidos]

    def situacao_documental(self) -> dict[str, list]:
        """As exigências em três grupos, para a tela não confundir os estados.

        Um documento enviado e ainda não conferido aparecia como "faltando" —
        e, como o subtipo tem outro nome, parecia um segundo documento.
        """
        por_tipo: dict[int, list] = {}
        for documento in self.documentos.select_related("tipo", "subtipo"):
            por_tipo.setdefault(documento.tipo_id, []).append(documento)

        aprovados, em_analise, com_problema, faltando = [], [], [], []
        recusados = {StatusDocumento.REJEITADO, StatusDocumento.FALHA_ANALISE}

        for tipo in self.documentos_exigidos():
            documentos = por_tipo.get(tipo.id, [])
            if not documentos:
                faltando.append(tipo)
            elif any(d.esta_vigente for d in documentos):
                aprovados.extend(d for d in documentos if d.esta_vigente)
            elif any(
                d.status in recusados or (d.esta_vencido and not d.em_analise) for d in documentos
            ):
                # Rejeitado é problema a corrigir. Vencido só depois de conferido:
                # antes disso quem decide se o prazo passa é a triagem (AGENTS.md D55),
                # e chamar de "precisa de correção" antecipava a decisão dela.
                com_problema.extend(documentos)
            else:
                em_analise.extend(documentos)

        return {
            "aprovados": aprovados,
            "em_analise": em_analise,
            "com_problema": com_problema,
            "faltando": faltando,
        }

    def tipos_a_enviar(self) -> list[TipoDocumento]:
        """O que ainda precisa de envio: nada vinculado, ou o que foi recusado."""
        situacao = self.situacao_documental()
        tipos = list(situacao["faltando"])
        tipos.extend(documento.tipo for documento in situacao["com_problema"])
        return tipos

    @property
    def documentacao_completa(self) -> bool:
        """Tudo aprovado e vigente. É o que libera o contrato para assinatura."""
        return not self.documentos_pendentes()

    @property
    def documentacao_entregue(self) -> bool:
        """Nada faltando e nada recusado: há o que analisar.

        Diferente de `documentacao_completa`, que exige aprovação. É esta que
        libera as **etapas** do contrato: quem confere o Termo de Adesão é a
        revisão jurídica, e exigir uma triagem antes dela pedia a mesma
        conferência duas vezes, de duas áreas (AGENTS.md §4.9).
        """
        situacao = self.situacao_documental()
        return not situacao["faltando"] and not situacao["com_problema"]


class EtapaAprovacao(models.Model):
    """Instância de etapa gerada para a operação a partir do enquadramento."""

    operacao = models.ForeignKey(Operacao, on_delete=models.CASCADE, related_name="etapas")
    etapa = models.CharField(max_length=32, choices=Etapa.choices)
    status = models.CharField(
        max_length=32, choices=StatusEtapa.choices, default=StatusEtapa.PENDENTE
    )
    parecer = models.TextField(
        blank=True,
        help_text="Obrigatório para aprovar ou reprovar. Registra a decisão humana.",
    )
    decidida_por = models.ForeignKey(
        "contas.Usuario", on_delete=models.PROTECT, null=True, blank=True
    )
    data_decisao = models.DateTimeField("data da decisão", null=True, blank=True)

    class Meta:
        verbose_name = "etapa de aprovação"
        verbose_name_plural = "etapas de aprovação"
        unique_together = ("operacao", "etapa")
        ordering = ("operacao", "id")

    def __str__(self) -> str:
        return f"{self.get_etapa_display()}: {self.get_status_display()}"

    @property
    def papel_responsavel(self) -> str:
        return PAPEL_RESPONSAVEL[Etapa(self.etapa)]

    @property
    def esta_decidida(self) -> bool:
        return self.status in {
            StatusEtapa.APROVADA,
            StatusEtapa.REPROVADA,
            StatusEtapa.DISPENSADA,
            StatusEtapa.REGISTRADA_EXTERNAMENTE,
            StatusEtapa.CUMPRIDA_NA_HABILITACAO,
        }

    @property
    def veio_da_habilitacao(self) -> bool:
        return self.status == StatusEtapa.CUMPRIDA_NA_HABILITACAO
