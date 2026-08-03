"""
Catálogo de tipos de documento (AGENTS.md §4.5).

Os tipos são dados de tabela, editáveis no Admin — nunca constantes no código.
O Kit Cadastral PJ pertence à contraparte; os demais, à operação.
"""

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import models


class EscopoDocumento(models.TextChoices):
    CADASTRAL = "cadastral", "Cadastral (contraparte)"
    OPERACIONAL = "operacional", "Operacional (operação)"


class StatusDocumento(models.TextChoices):
    ENVIADO = "enviado", "Enviado"
    PROCESSANDO = "processando", "Processando"
    ANALISADO = "analisado", "Analisado"
    APROVADO = "aprovado", "Aprovado"
    REJEITADO = "rejeitado", "Rejeitado"
    FALHA_ANALISE = "falha_analise", "Falha na análise"


class TipoPessoa(models.TextChoices):
    """Deduzido do documento informado no formulário, nunca perguntado."""

    FISICA = "pf", "Pessoa física"
    JURIDICA = "pj", "Pessoa jurídica"


class TipoDocumento(models.Model):
    nome = models.CharField(max_length=120, unique=True)
    escopo = models.CharField(max_length=16, choices=EscopoDocumento.choices)
    kit_cadastral_pj = models.BooleanField(
        "compõe o Kit Cadastral PJ",
        default=False,
        help_text="Documentação base exigida de toda contraparte pessoa jurídica.",
    )
    obrigatorio_no_kit = models.BooleanField(
        "obrigatório no kit",
        default=True,
        help_text="Desmarque para itens condicionais, como a procuração, exigida "
        "apenas 'quando houver' — não contam como pendência do dossiê.",
    )
    dias_validade = models.PositiveIntegerField(
        "validade (dias)",
        null=True,
        blank=True,
        help_text=(
            "Prazo de vigência a partir da data de emissão. Ex.: comprovante de "
            "endereço, 90 dias. Em branco, o documento não vence."
        ),
    )
    exige_data_emissao = models.BooleanField(
        "exige data de emissão",
        default=True,
        help_text="Desmarque quando a emissão não define a validade — o RG, por exemplo.",
    )
    aceita_multiplos_arquivos = models.BooleanField(
        "aceita vários arquivos",
        default=True,
        help_text="Frente e verso, páginas separadas, anexos do mesmo documento.",
    )
    observacao = models.TextField("observação", blank=True)
    ativo = models.BooleanField(default=True)

    class Meta:
        verbose_name = "tipo de documento"
        verbose_name_plural = "tipos de documento"
        ordering = ("escopo", "nome")

    def __str__(self) -> str:
        return self.nome


class SubtipoDocumento(models.Model):
    """Qual documento foi enviado dentro de um tipo genérico.

    "Documento de identificação" pode ser RG, CNH, passaporte... Saber qual é
    torna a extração por IA mais precisa, porque cada um tem layout próprio.
    """

    tipo_documento = models.ForeignKey(
        TipoDocumento, on_delete=models.CASCADE, related_name="subtipos"
    )
    nome = models.CharField(max_length=80)
    tem_validade_propria = models.BooleanField(
        default=False,
        help_text="CNH e passaporte vencem; RG não. Define se pedimos a data de validade.",
    )
    ativo = models.BooleanField(default=True)

    class Meta:
        verbose_name = "subtipo de documento"
        verbose_name_plural = "subtipos de documento"
        ordering = ("tipo_documento__nome", "nome")
        unique_together = ("tipo_documento", "nome")

    def __str__(self) -> str:
        return self.nome


class ExigenciaCadastral(models.Model):
    """Que documento o kit cadastral exige, por tipo de pessoa e faixa de valor.

    Dado em tabela, como toda regra (AGENTS.md §4.4). Exemplo: PF acima de
    R$ 4.000,00 precisa comprovar renda (§4.5, D20).

    Faixa **inclusiva nos dois extremos**: "acima de R$ 4.000,00" é
    `valor_minimo = 4000.01`.
    """

    tipo_pessoa = models.CharField("tipo de pessoa", max_length=2, choices=TipoPessoa.choices)
    tipo_documento = models.ForeignKey(TipoDocumento, on_delete=models.PROTECT)
    valor_minimo = models.DecimalField(
        "valor mínimo",
        max_digits=14,
        decimal_places=2,
        default=Decimal("0.00"),
        help_text="Inclusivo. Zero significa que vale para qualquer valor.",
    )
    valor_maximo = models.DecimalField(
        "valor máximo",
        max_digits=14,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Inclusivo. Em branco, não há limite superior.",
    )
    obrigatorio = models.BooleanField(
        default=True,
        help_text="Desmarque para itens condicionais, como a procuração "
        "('quando houver') — não contam como pendência.",
    )
    grupo_alternativo = models.CharField(
        max_length=50,
        blank=True,
        help_text="Documentos com o mesmo grupo se substituem: basta um deles. "
        "Ex.: holerite OU declaração de IR.",
    )
    ativa = models.BooleanField(default=True)

    class Meta:
        verbose_name = "exigência cadastral"
        verbose_name_plural = "exigências cadastrais"
        ordering = ("tipo_pessoa", "valor_minimo", "tipo_documento__nome")

    def __str__(self) -> str:
        return f"{self.get_tipo_pessoa_display()} — {self.tipo_documento}"

    def clean(self):
        if self.valor_maximo is not None and self.valor_maximo < self.valor_minimo:
            raise ValidationError(
                {"valor_maximo": "O valor máximo não pode ser menor que o mínimo."}
            )
        if self.tipo_documento_id and self.tipo_documento.escopo != EscopoDocumento.CADASTRAL:
            raise ValidationError(
                {"tipo_documento": "O kit cadastral só aceita tipo de escopo cadastral."}
            )

    def cobre(self, valor: Decimal | None) -> bool:
        """A exigência vale para este valor? Sem valor informado, só o que não tem faixa."""
        if valor is None:
            return self.valor_minimo == Decimal("0.00")
        if valor < self.valor_minimo:
            return False
        return self.valor_maximo is None or valor <= self.valor_maximo
