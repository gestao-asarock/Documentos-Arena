"""
Conferência jurídica do contrato (AGENTS.md §4.9).

No fluxo piloto a análise é simples e objetiva: o **Termo de Adesão** vem pronto
do Clube, e o Jurídico confere se ele reflete o que foi registrado na operação.
Divergência em qualquer destes campos muda o negócio — valor cobrado, data
reservada, quem assina — e por isso são eles que vão para a tela, lado a lado.

Quando a análise por IA entrar, ela preenche a coluna "no documento"; a
conferência continua sendo humana (AGENTS.md §5.1).
"""

from dataclasses import dataclass

from .templatetags.formatacao import cpf_cnpj, data_br, moeda


@dataclass
class CampoConferencia:
    """Um campo a comparar. `valor` já vem formatado como aparece no termo."""

    rotulo: str
    valor: str
    observacao: str = ""


def campos_do_contrato(operacao) -> list[CampoConferencia]:
    """O que o Termo de Adesão precisa repetir, exatamente."""
    contraparte = operacao.contraparte
    campos = [
        CampoConferencia("Nome do contratante", contraparte.nome),
        CampoConferencia("CPF/CNPJ", cpf_cnpj(contraparte.documento)),
    ]

    if contraparte.rg:
        campos.append(CampoConferencia("RG", contraparte.rg))
    if contraparte.endereco:
        campos.append(CampoConferencia("Endereço", contraparte.endereco))
    if contraparte.email:
        campos.append(CampoConferencia("E-mail", contraparte.email))

    # Formatado como no termo: comparar "R$ 1.500,00" com "1500.00" atrapalha
    # justamente quem está conferindo (AGENTS.md §8).
    campos.append(
        CampoConferencia(
            "Valor",
            moeda(operacao.valor_total),
            "Divergência aqui muda o que será cobrado.",
        )
    )
    if operacao.data_evento:
        campos.append(
            CampoConferencia(
                "Data do evento",
                data_br(operacao.data_evento),
                "Alteração de data implica multa de 50% no contrato-mãe.",
            )
        )
    if operacao.horario_evento:
        campos.append(CampoConferencia("Horário", operacao.horario_evento.strftime("%H:%M")))

    return campos
