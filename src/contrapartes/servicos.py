"""
Estado do perfil da contraparte, derivado do dossiê (AGENTS.md §4.6, D29).

O documento cadastral pertence à **contraparte**, não ao cadastro que o enviou:
é o que permite reaproveitá-lo em perfis e contratos seguintes. A consequência é
que a situação da habilitação não pode ser atualizada só quando alguém aprova um
documento — um perfil novo pode nascer com o kit inteiro já aprovado, sem que
nenhuma aprovação vá acontecer. Por isso o estado é **derivado do dossiê**,
sempre que se olha para ele, como já se faz com a operação em `operacoes.servicos.avancar`.
"""

from dataclasses import dataclass

from django.db import transaction
from django.utils import timezone

from auditoria.servicos import Acao, registrar
from documentos.models import StatusDocumento

from .models import Contraparte, Habilitacao, StatusHabilitacao

#: Estados que a conferência documental não governa mais. Depois que o perfil
#: passa para o crédito, aprovar um documento não pode puxá-lo de volta para o
#: compliance — quem decide dali em diante é o parecer, não o dossiê.
ESTADOS_ALEM_DA_CONFERENCIA = frozenset(
    {
        StatusHabilitacao.EM_CREDITO,
        StatusHabilitacao.HABILITADA,
        StatusHabilitacao.RECUSADA,
    }
)


def avancar_habilitacao(habilitacao: Habilitacao | None, *, usuario=None) -> Habilitacao | None:
    """Põe a habilitação no estado que o dossiê da contraparte descreve.

    Kit completo e sem rejeição → segue para o compliance. Documento esperando
    conferência → análise documental. Documento rejeitado → pendência. Nada
    enviado → aguardando documentos.

    Idempotente: sem mudança de estado, não grava nem registra nada.
    """
    if habilitacao is None or habilitacao.status in ESTADOS_ALEM_DA_CONFERENCIA:
        return habilitacao

    contraparte = habilitacao.contraparte
    documentos = contraparte.documentos_cadastrais

    if documentos.filter(status=StatusDocumento.REJEITADO).exists():
        novo = StatusHabilitacao.COM_PENDENCIA
    elif contraparte.kit_completo():
        novo = StatusHabilitacao.EM_COMPLIANCE
    elif documentos.filter(
        status__in=[StatusDocumento.ENVIADO, StatusDocumento.PROCESSANDO]
    ).exists():
        novo = StatusHabilitacao.EM_ANALISE_DOCUMENTAL
    else:
        novo = StatusHabilitacao.AGUARDANDO_DOCUMENTOS

    if habilitacao.status == novo:
        return habilitacao

    anterior = habilitacao.get_status_display()
    habilitacao.status = novo
    habilitacao.save()
    registrar(
        acao=Acao.TRANSICAO_ESTADO,
        descricao=(
            f"Habilitação da contraparte #{contraparte.pk}: "
            f"{anterior} → {habilitacao.get_status_display()}"
        ),
        objeto=habilitacao,
        usuario=usuario,
    )
    return habilitacao


#: Campos que os documentos do kit **comprovam**: é contra eles que a triagem
#: confere o RG e o comprovante de residência. Mudar qualquer um invalida a
#: conferência já feita, e por isso reinicia a validação (AGENTS.md D47).
#: E-mail, telefone e nome fantasia ficam de fora de propósito: nenhum documento
#: os atesta, e refazer compliance por causa de um telefone é custo sem ganho.
CAMPOS_PROVADOS_POR_DOCUMENTO = {
    "nome": "nome",
    "data_nascimento": "data de nascimento",
    "rg": "RG",
    "cep": "CEP",
    "logradouro": "logradouro",
    "numero": "número",
    "complemento": "complemento",
    "bairro": "bairro",
    "cidade": "cidade",
    "uf": "UF",
}

#: Alteráveis mas sem efeito sobre a validação.
CAMPOS_DE_CONTATO = {
    "email": "e-mail",
    "telefone": "telefone",
    "nome_fantasia": "nome fantasia",
}


def _mudou(atual, novo) -> bool:
    """Compara ignorando espaço em volta e a diferença entre `None` e `""`."""
    if isinstance(atual, str) or isinstance(novo, str):
        return (atual or "").strip() != (novo or "").strip()
    return atual != novo


def _texto(valor) -> str:
    """Valor como a tela o mostra, para a coluna "de" e "para" da confirmação."""
    if valor is None or valor == "":
        return "(vazio)"
    if hasattr(valor, "strftime"):
        return valor.strftime("%d/%m/%Y")
    return str(valor)


@dataclass(frozen=True)
class Mudanca:
    """Um campo que muda, com o valor de antes e o de depois."""

    campo: str
    rotulo: str
    antes: str
    depois: str


@dataclass(frozen=True)
class Alteracao:
    """O que muda numa edição de cadastro. Serve de prévia e de resultado."""

    mudancas: list[Mudanca]

    def __bool__(self) -> bool:
        return bool(self.mudancas)

    @property
    def rotulos(self) -> list[str]:
        return [m.rotulo for m in self.mudancas]

    @property
    def resumo(self) -> str:
        return ", ".join(self.rotulos)

    @property
    def exige_revalidacao(self) -> bool:
        """A mudança derruba a conferência já feita?"""
        return any(m.campo in CAMPOS_PROVADOS_POR_DOCUMENTO for m in self.mudancas)


def comparar_cadastro(contraparte: Contraparte, dados: dict) -> Alteracao:
    """O que mudaria, **sem gravar nada**.

    É o que a tela de confirmação mostra antes de a pessoa decidir: ninguém
    confirma um efeito grande sem ver exatamente o que vai mudar.
    """
    rotulos = {**CAMPOS_PROVADOS_POR_DOCUMENTO, **CAMPOS_DE_CONTATO}
    return Alteracao(
        mudancas=[
            Mudanca(
                campo=campo,
                rotulo=rotulos[campo],
                antes=_texto(getattr(contraparte, campo)),
                depois=_texto(valor),
            )
            for campo, valor in dados.items()
            if campo in rotulos and _mudou(getattr(contraparte, campo), valor)
        ]
    )


def efeitos_da_revalidacao(habilitacao: Habilitacao | None) -> dict:
    """O que o reinício vai desfazer, contado antes de desfazer.

    A tela de confirmação diz isto em números: "2 documentos voltam para a
    triagem", e não um genérico "as análises serão refeitas".
    """
    from compliance.models import ParecerCompliance
    from compliance.models import StatusParecer as StatusCompliance
    from credito.models import ParecerCredito
    from credito.models import StatusParecer as StatusCredito

    if habilitacao is None:
        return {"documentos": 0, "pareceres": [], "etapa": ""}

    pareceres = []
    if ParecerCompliance.objects.filter(
        habilitacao=habilitacao, status=StatusCompliance.CONCLUIDO
    ).exists():
        pareceres.append("Due diligence (compliance)")
    if ParecerCredito.objects.filter(
        contraparte=habilitacao.contraparte, status=StatusCredito.CONCLUIDO
    ).exists():
        pareceres.append("Risco e crédito")

    return {
        "documentos": habilitacao.contraparte.documentos_cadastrais.filter(
            status=StatusDocumento.APROVADO
        ).count(),
        "pareceres": pareceres,
        "etapa": habilitacao.get_status_display(),
    }


@transaction.atomic
def alterar_dados_cadastrais(contraparte: Contraparte, dados: dict, *, usuario=None) -> Alteracao:
    """Aplica a edição do cadastro e diz o que mudou.

    O CPF/CNPJ não entra aqui nem por engano: ele é a identidade da contraparte
    e a chave do reaproveitamento entre perfis e contratos (AGENTS.md D47). Quem
    chama decide o que fazer com a validação, olhando `exige_revalidacao`.

    Nada mudou? Não grava e não registra: edição aberta e fechada sem alteração
    não pode sujar a auditoria nem mexer na marca de alteração.
    """
    alteracao = comparar_cadastro(contraparte, dados)
    if not alteracao:
        return alteracao

    for mudanca in alteracao.mudancas:
        setattr(contraparte, mudanca.campo, dados[mudanca.campo])

    if alteracao.exige_revalidacao:
        # Só marca quando a alteração é das que invalidam a conferência: é essa
        # marca que a triagem lê para saber por que o documento voltou.
        contraparte.data_alteracao_cadastral = timezone.now()
        contraparte.alterada_por = usuario if getattr(usuario, "pk", None) else None
        contraparte.campos_alterados = alteracao.resumo[:255]

    contraparte.save()
    registrar(
        acao=Acao.ALTERACAO_CADASTRAL,
        # Rótulo do campo, nunca o valor: o conteúdo é dado pessoal (AGENTS.md §6).
        descricao=f"Cadastro da contraparte #{contraparte.pk} alterado: {alteracao.resumo}",
        objeto=contraparte,
        usuario=usuario,
    )
    return alteracao


@transaction.atomic
def reiniciar_validacao(habilitacao: Habilitacao, *, usuario=None, motivo: str = "") -> Habilitacao:
    """Devolve o perfil ao começo da esteira, depois de o cadastro mudar.

    Os arquivos **ficam**: o que se perde é a aprovação deles. Um documento
    aprovado atestava os dados de antes; contra os dados novos ele ainda não foi
    conferido, e por isso volta para a fila da triagem em vez de ser apagado.

    Pareceres concluídos voltam a rascunho, com o texto e as evidências
    preservados — quem revisar corrige o que mudou em vez de redigitar nove
    blocos. A conclusão anterior fica na auditoria.
    """
    # Importados aqui dentro: `compliance` e `credito` já dependem de
    # `contrapartes`, e no topo do módulo isto seria import circular.
    from compliance.models import ParecerCompliance
    from compliance.models import StatusParecer as StatusCompliance
    from credito.models import ParecerCredito
    from credito.models import StatusParecer as StatusCredito

    contraparte = habilitacao.contraparte

    devolvidos = contraparte.documentos_cadastrais.filter(status=StatusDocumento.APROVADO).update(
        status=StatusDocumento.ENVIADO
    )

    ParecerCompliance.objects.filter(
        habilitacao=habilitacao, status=StatusCompliance.CONCLUIDO
    ).update(status=StatusCompliance.RASCUNHO, data_conclusao=None)
    ParecerCredito.objects.filter(contraparte=contraparte, status=StatusCredito.CONCLUIDO).update(
        status=StatusCredito.RASCUNHO, data_conclusao=None
    )

    habilitacao.status = StatusHabilitacao.AGUARDANDO_DOCUMENTOS
    habilitacao.data_conclusao = None
    habilitacao.save()
    # Perfil que já apontava para contrato deixa de apontar.
    habilitacao.solicitacoes.exclude(status="cancelada").update(status="em_habilitacao")

    registrar(
        acao=Acao.TRANSICAO_ESTADO,
        descricao=(
            f"Validação do perfil da contraparte #{contraparte.pk} reiniciada"
            f"{f' ({motivo})' if motivo else ''}: "
            f"{devolvidos} documento{'s' if devolvidos != 1 else ''} de volta à triagem"
        ),
        objeto=habilitacao,
        usuario=usuario,
    )

    # O estado real sai do dossiê, como sempre: com documento na fila isto vira
    # "em análise documental"; sem nenhum, fica em "aguardando documentos".
    return avancar_habilitacao(habilitacao, usuario=usuario)


__all__ = [
    "CAMPOS_DE_CONTATO",
    "CAMPOS_PROVADOS_POR_DOCUMENTO",
    "ESTADOS_ALEM_DA_CONFERENCIA",
    "Alteracao",
    "Mudanca",
    "alterar_dados_cadastrais",
    "avancar_habilitacao",
    "comparar_cadastro",
    "efeitos_da_revalidacao",
    "reiniciar_validacao",
]
