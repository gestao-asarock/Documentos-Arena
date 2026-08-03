"""
Contraparte, dossiê cadastral e habilitação (AGENTS.md §4.0, §4.5, D10 e D19).

A contraparte **não é usuária do sistema**: quem opera é o Clube, em nome dela.
A habilitação (Fase 1) pertence à contraparte e é reaproveitada entre contratos.
"""

from datetime import timedelta
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from documentos.models import (
    ExigenciaCadastral,
    StatusDocumento,
    SubtipoDocumento,
    TipoDocumento,
    TipoPessoa,
)


def deduzir_tipo_pessoa(documento: str) -> str:
    """CPF (11 dígitos) ou CNPJ (14). O usuário não escolhe — o documento diz.

    Levanta `ValueError` para qualquer coisa que não seja um dos dois tamanhos.
    """
    digitos = "".join(c for c in (documento or "") if c.isdigit())
    if len(digitos) == 11:
        return TipoPessoa.FISICA
    if len(digitos) == 14:
        return TipoPessoa.JURIDICA
    raise ValueError("Informe um CPF (11 dígitos) ou um CNPJ (14 dígitos).")


def apenas_digitos(documento: str) -> str:
    return "".join(c for c in (documento or "") if c.isdigit())


def caminho_do_arquivo(instancia, nome_original: str) -> str:
    """Nome de arquivo não adivinhável (AGENTS.md §5.4).

    Guardar `rg-joao-silva.jpg` expõe o titular pelo próprio nome e torna a URL
    fácil de chutar. O nome original fica no banco, para exibição.
    """
    extensao = Path(nome_original).suffix.lower()[:10]
    hoje = timezone.localdate()
    return f"cadastral/{hoje:%Y/%m}/{uuid4().hex}{extensao}"


class Contraparte(models.Model):
    tipo_pessoa = models.CharField(
        "tipo de pessoa",
        max_length=2,
        choices=TipoPessoa.choices,
        help_text="Preenchido automaticamente a partir do CPF/CNPJ.",
    )
    nome = models.CharField(max_length=200, help_text="Razão social, no caso de PJ.")
    nome_fantasia = models.CharField(max_length=200, blank=True)
    documento = models.CharField(
        "CPF/CNPJ", max_length=18, unique=True, help_text="Somente dígitos."
    )

    # Dados declarados no formulário — é contra eles que a IA confronta os
    # documentos enviados (AGENTS.md §4.6).
    data_nascimento = models.DateField("data de nascimento", null=True, blank=True)
    rg = models.CharField("RG", max_length=20, blank=True)
    email = models.EmailField("e-mail", blank=True)
    telefone = models.CharField(max_length=20, blank=True)

    # Endereço estruturado: texto livre inviabiliza o confronto automático com o
    # comprovante de residência (AGENTS.md §4.6).
    cep = models.CharField("CEP", max_length=9, blank=True)
    logradouro = models.CharField(max_length=200, blank=True)
    numero = models.CharField("número", max_length=20, blank=True)
    complemento = models.CharField(max_length=100, blank=True)
    bairro = models.CharField(max_length=100, blank=True)
    cidade = models.CharField(max_length=100, blank=True)
    uf = models.CharField("UF", max_length=2, blank=True)

    # Governança de partes relacionadas está "em discussão" no guia: por ora isto é
    # apenas um alerta em tela para o Compliance, sem alçada especial (AGENTS.md D14).
    parte_relacionada = models.BooleanField(
        default=False,
        help_text="Marque se houver vínculo com o Fundo, o Clube ou a gestora. "
        "Gera alerta para o Compliance; não altera a alçada.",
    )

    ativa = models.BooleanField(default=True)
    data_criacao = models.DateTimeField(auto_now_add=True)
    data_atualizacao = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "contraparte"
        verbose_name_plural = "contrapartes"
        ordering = ("nome",)

    def __str__(self) -> str:
        return f"{self.nome} ({self.documento})"

    def save(self, *args, **kwargs):
        self.documento = apenas_digitos(self.documento)
        if not self.tipo_pessoa:
            self.tipo_pessoa = deduzir_tipo_pessoa(self.documento)
        super().save(*args, **kwargs)

    @property
    def eh_pj(self) -> bool:
        return self.tipo_pessoa == TipoPessoa.JURIDICA

    @property
    def endereco(self) -> str:
        """Endereço em uma linha, para exibição."""
        partes = [
            ", ".join(p for p in (self.logradouro, self.numero) if p),
            self.complemento,
            self.bairro,
            " - ".join(p for p in (self.cidade, self.uf) if p),
            self.cep,
        ]
        return " · ".join(p for p in partes if p)

    # -- Dossiê cadastral ----------------------------------------------------

    def exigencias_cadastrais(self, valor: Decimal | None = None) -> list[ExigenciaCadastral]:
        """Exigências aplicáveis a esta contraparte.

        Sem valor, devolve o **kit base do perfil** — o que vale para qualquer
        operação. Com valor, acrescenta o que aquela faixa exige, como a
        comprovação de renda de PF acima de R$ 4.000,00 (AGENTS.md §4.5, D20).
        """
        return [
            exigencia
            for exigencia in ExigenciaCadastral.objects.filter(
                tipo_pessoa=self.tipo_pessoa, ativa=True
            ).select_related("tipo_documento")
            if exigencia.cobre(valor)
        ]

    def documentos_validos_de(self, tipos) -> dict[int, list]:
        """Documentos já aprovados e vigentes, por tipo.

        É o que permite reaproveitar em operação nova o que já foi conferido
        antes: o documento pertence ao perfil, não ao contrato (AGENTS.md D29).
        """
        ids = {tipo.id for tipo in tipos}
        aproveitaveis: dict[int, list] = {}
        for documento in self.documentos_cadastrais.select_related("tipo", "subtipo"):
            if documento.tipo_id in ids and documento.esta_vigente:
                aproveitaveis.setdefault(documento.tipo_id, []).append(documento)
        return aproveitaveis

    def _tipos_vigentes(self) -> set[int]:
        return {d.tipo_id for d in self.documentos_cadastrais.all() if d.esta_vigente}

    def pendencias_cadastrais(self, valor: Decimal | None = None) -> list[TipoDocumento]:
        """O que falta ou venceu, considerando alternativas equivalentes.

        Documentos de um mesmo `grupo_alternativo` se substituem: holerite **ou**
        declaração de IR satisfaz a exigência de renda (AGENTS.md §4.5).
        """
        vigentes = self._tipos_vigentes()
        pendentes: list[TipoDocumento] = []
        grupos_satisfeitos: set[str] = set()
        grupos_pendentes: dict[str, list[TipoDocumento]] = {}

        for exigencia in self.exigencias_cadastrais(valor):
            if not exigencia.obrigatorio:
                continue

            tipo = exigencia.tipo_documento
            atendida = tipo.id in vigentes

            if not exigencia.grupo_alternativo:
                if not atendida:
                    pendentes.append(tipo)
                continue

            if atendida:
                grupos_satisfeitos.add(exigencia.grupo_alternativo)
            else:
                grupos_pendentes.setdefault(exigencia.grupo_alternativo, []).append(tipo)

        for grupo, tipos in grupos_pendentes.items():
            if grupo not in grupos_satisfeitos:
                pendentes.extend(tipos)

        return pendentes

    def kit_completo(self, valor: Decimal | None = None) -> bool:
        return not self.pendencias_cadastrais(valor)

    def situacao_do_kit(self, valor: Decimal | None = None) -> dict[str, list]:
        """O kit em três grupos, para a tela: o que falta, o que está em análise, o que valeu.

        Um documento enviado sai de "faltando" mesmo antes de aprovado — quem
        enviou precisa ver que o envio chegou (AGENTS.md §4.10).
        """
        enviados: dict[int, list] = {}
        for documento in self.documentos_cadastrais.select_related("tipo", "subtipo"):
            enviados.setdefault(documento.tipo_id, []).append(documento)

        faltando, em_analise, vigentes, com_problema = [], [], [], []

        for tipo in self.pendencias_cadastrais(valor):
            documentos = enviados.get(tipo.id, [])
            if not documentos:
                faltando.append(tipo)
                continue
            for documento in documentos:
                if documento.em_analise:
                    em_analise.append(documento)
                else:
                    # Rejeitado, vencido ou falha de análise: precisa de ação.
                    com_problema.append(documento)

        pendentes = {tipo.id for tipo in self.pendencias_cadastrais(valor)}
        for tipo_id, documentos in enviados.items():
            if tipo_id in pendentes:
                continue
            vigentes.extend(d for d in documentos if d.esta_vigente)

        return {
            "faltando": faltando,
            "em_analise": em_analise,
            "com_problema": com_problema,
            "vigentes": vigentes,
        }

    @property
    def habilitacao_vigente(self):
        """Habilitação concluída e dentro do prazo, se houver."""
        for habilitacao in self.habilitacoes.all():
            if habilitacao.esta_vigente:
                return habilitacao
        return None

    @property
    def esta_habilitada(self) -> bool:
        return self.habilitacao_vigente is not None


class StatusHabilitacao(models.TextChoices):
    """Situação do **perfil** da contraparte (AGENTS.md §4.0, D29)."""

    AGUARDANDO_DOCUMENTOS = "aguardando_documentos", "Aguardando documentos"
    EM_ANALISE_DOCUMENTAL = "em_analise_documental", "Em análise documental"
    COM_PENDENCIA = "com_pendencia", "Com pendência"
    EM_COMPLIANCE = "em_compliance", "Em análise de compliance"
    HABILITADA = "habilitada", "Perfil validado"
    RECUSADA = "recusada", "Recusado"


class Habilitacao(models.Model):
    """Validação do perfil da contraparte — só documentos base e compliance.

    O perfil não conhece valor nem evento: por isso serve a qualquer contrato
    futuro, enquanto os documentos estiverem vigentes (AGENTS.md D29). A análise
    de crédito não mora aqui — ela depende do valor e pertence à operação (D30).
    """

    contraparte = models.ForeignKey(
        Contraparte, on_delete=models.CASCADE, related_name="habilitacoes"
    )
    status = models.CharField(
        max_length=32,
        choices=StatusHabilitacao.choices,
        default=StatusHabilitacao.AGUARDANDO_DOCUMENTOS,
    )
    data_conclusao = models.DateTimeField("data da conclusão", null=True, blank=True)
    data_validade = models.DateField(
        "válida até",
        null=True,
        blank=True,
        help_text="Prazo a definir com o compliance. Em branco, não expira por tempo.",
    )
    motivo_recusa = models.TextField("motivo da recusa", blank=True)
    data_criacao = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "habilitação"
        verbose_name_plural = "habilitações"
        ordering = ("-data_criacao",)

    def __str__(self) -> str:
        return f"{self.contraparte.nome} — {self.get_status_display()}"

    @property
    def esta_vigente(self) -> bool:
        if self.status != StatusHabilitacao.HABILITADA:
            return False
        return self.data_validade is None or self.data_validade >= timezone.localdate()


class DocumentoCadastral(models.Model):
    """Documento do kit cadastral, pertencente à contraparte."""

    contraparte = models.ForeignKey(
        Contraparte, on_delete=models.CASCADE, related_name="documentos_cadastrais"
    )
    tipo = models.ForeignKey(TipoDocumento, on_delete=models.PROTECT)
    subtipo = models.ForeignKey(
        SubtipoDocumento,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        help_text="Qual documento é, dentro do tipo: RG, CNH, passaporte...",
    )
    status = models.CharField(
        max_length=16, choices=StatusDocumento.choices, default=StatusDocumento.ENVIADO
    )
    data_emissao = models.DateField(
        "data de emissão",
        null=True,
        blank=True,
        help_text="Base para o cálculo de vigência. Pode vir da extração por IA.",
    )
    data_envio = models.DateTimeField(auto_now_add=True)
    enviado_por = models.ForeignKey(
        "contas.Usuario", on_delete=models.PROTECT, null=True, blank=True
    )
    observacao = models.TextField("observação", blank=True)

    class Meta:
        verbose_name = "documento cadastral"
        verbose_name_plural = "documentos cadastrais"
        ordering = ("-data_envio",)

    def __str__(self) -> str:
        rotulo = self.subtipo or self.tipo
        return f"{rotulo} — {self.contraparte.nome}"

    def clean(self):
        # Documento complementar (escopo operacional) também pertence ao perfil:
        # ele é reaproveitado entre operações do mesmo tipo (AGENTS.md D29).
        if self.subtipo_id and self.subtipo.tipo_documento_id != self.tipo_id:
            raise ValidationError({"subtipo": "O subtipo não pertence a este tipo de documento."})

    @property
    def rotulo(self) -> str:
        """Nome do subtipo quando houver — 'CNH' diz mais que 'identificação'."""
        return str(self.subtipo) if self.subtipo_id else str(self.tipo)

    @property
    def em_analise(self) -> bool:
        return self.status in {StatusDocumento.ENVIADO, StatusDocumento.PROCESSANDO}

    @property
    def data_vencimento(self):
        """Data em que o documento deixa de valer, ou None se não vence."""
        if not self.tipo.dias_validade or not self.data_emissao:
            return None
        return self.data_emissao + timedelta(days=self.tipo.dias_validade)

    @property
    def esta_vencido(self) -> bool:
        vencimento = self.data_vencimento
        return vencimento is not None and vencimento < timezone.localdate()

    @property
    def esta_vigente(self) -> bool:
        """Vale para compor o dossiê: aprovado e dentro do prazo.

        Estar completo não é estar aprovado — são estados distintos (AGENTS.md §4.5).
        """
        return self.status == StatusDocumento.APROVADO and not self.esta_vencido


class ArquivoDocumento(models.Model):
    """Um arquivo de um documento.

    Frente e verso do RG são o mesmo documento em dois arquivos — exigir dois
    envios separados só piora a vida de quem opera.
    """

    documento = models.ForeignKey(
        DocumentoCadastral, on_delete=models.CASCADE, related_name="arquivos"
    )
    arquivo = models.FileField(upload_to=caminho_do_arquivo)
    nome_original = models.CharField(
        max_length=255, blank=True, help_text="Nome que o usuário enviou, só para exibição."
    )
    ordem = models.PositiveSmallIntegerField(default=0)
    data_envio = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "arquivo do documento"
        verbose_name_plural = "arquivos do documento"
        ordering = ("documento", "ordem")

    def __str__(self) -> str:
        return self.nome_original or self.arquivo.name
