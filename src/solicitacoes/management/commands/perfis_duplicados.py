"""
Resolve os perfis duplicados que já estão no banco (AGENTS.md D57).

Até o D57 nada impedia dois cadastros com o mesmo CPF/CNPJ, e o segundo nascia
validado de graça: a habilitação é da contraparte e era reaproveitada inteira.
A regra nova barra o cadastro na entrada, mas não conserta o que já entrou, e
com duplicata na base a tela passa a dizer "já existe" apontando para um perfil
enquanto o outro segue vivo ao lado.

Este comando mantém **um** perfil por contraparte e cancela os demais. Nada é
apagado: o registro fica, com motivo e data, e sai da esteira ativa. Por padrão
só relata; `--aplicar` grava.

    python manage.py perfis_duplicados
    python manage.py perfis_duplicados --aplicar
"""

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from auditoria.servicos import Acao, registrar
from contrapartes.models import StatusHabilitacao
from solicitacoes.models import Solicitacao, StatusSolicitacao
from solicitacoes.servicos import STATUS_QUE_OCUPAM_O_DOCUMENTO

#: Motivo gravado no perfil cancelado. Fica no registro e na tela: quem abrir o
#: duplicado depois precisa entender por que ele foi encerrado sem ninguém pedir.
MOTIVO = (
    "Cadastro duplicado da mesma contraparte, encerrado na limpeza de base. "
    "O perfil em uso desta contraparte é o #{mantido}."
)

#: Quanto cada situação avança na esteira. Entre dois duplicados fica o que foi
#: mais longe: cancelar o validado e manter o rascunho jogaria fora a análise.
AVANCO = {
    StatusSolicitacao.RASCUNHO: 0,
    StatusSolicitacao.EM_HABILITACAO: 1,
    StatusSolicitacao.PRONTA_PARA_CONTRATO: 2,
}

#: Habilitação nestes estados já terminou. Fora deles, a habilitação de um perfil
#: duplicado continua ocupando a fila de compliance ou de crédito mesmo depois de
#: o perfil ser cancelado: as filas leem `Habilitacao`, não `Solicitacao`.
HABILITACAO_ENCERRADA = {StatusHabilitacao.HABILITADA, StatusHabilitacao.RECUSADA}


def _ordem_de_preferencia(perfil: Solicitacao) -> tuple:
    """Melhor primeiro: mais avançado, depois com habilitação, depois o mais velho.

    O desempate pelo mais velho não é estético: é o perfil que tem histórico e
    é o que `servicos.perfil_ativo_de` devolve, então tela e comando concordam.
    """
    return (AVANCO.get(perfil.status, 0), perfil.habilitacao_id is not None, -perfil.pk)


class Command(BaseCommand):
    help = "Mantém um perfil por contraparte e cancela os cadastros duplicados."

    def add_arguments(self, parser):
        parser.add_argument(
            "--aplicar",
            action="store_true",
            help="Grava os cancelamentos. Sem isto, só relata.",
        )

    def handle(self, *args, **opcoes):
        aplicar = opcoes["aplicar"]

        por_contraparte: dict[int, list[Solicitacao]] = {}
        for perfil in (
            Solicitacao.objects.filter(status__in=STATUS_QUE_OCUPAM_O_DOCUMENTO)
            .select_related("contraparte", "habilitacao")
            .order_by("pk")
        ):
            por_contraparte.setdefault(perfil.contraparte_id, []).append(perfil)

        duplicados = {
            contraparte_id: perfis
            for contraparte_id, perfis in por_contraparte.items()
            if len(perfis) > 1
        }

        if not duplicados:
            sem_duplicata = "Nenhuma contraparte com mais de um perfil ativo."
            self.stdout.write(self.style.SUCCESS(sem_duplicata))
            return

        cancelados, filas_a_conferir = 0, []

        with transaction.atomic():
            for perfis in duplicados.values():
                em_ordem = sorted(perfis, key=_ordem_de_preferencia, reverse=True)
                mantido, resto = em_ordem[0], em_ordem[1:]
                contraparte = mantido.contraparte

                self.stdout.write(
                    f"\n{contraparte.documento}: {contraparte.nome} ({len(perfis)} perfis ativos)"
                )
                self.stdout.write(f"  manter   #{mantido.pk}: {mantido.get_status_display()}")

                for perfil in resto:
                    self.stdout.write(f"  cancelar #{perfil.pk}: {perfil.get_status_display()}")
                    if (
                        perfil.habilitacao_id
                        and perfil.habilitacao_id != mantido.habilitacao_id
                        and perfil.habilitacao.status not in HABILITACAO_ENCERRADA
                    ):
                        filas_a_conferir.append((perfil.pk, perfil.habilitacao))

                    if aplicar:
                        self._cancelar(perfil, mantido)
                    cancelados += 1

            if not aplicar:
                # Nada gravado: o relatório roda dentro da transação só para não
                # precisar de dois caminhos de código.
                transaction.set_rollback(True)

        self._resumo(duplicados, cancelados, filas_a_conferir, aplicar=aplicar)

    def _cancelar(self, perfil: Solicitacao, mantido: Solicitacao) -> None:
        """Encerra o duplicado.

        Não passa por `Solicitacao.cancelar`, e é de propósito: aquele método
        recusa cancelar perfil de contraparte com contrato em andamento, guarda
        que existe para não deixar um contrato sem o perfil que o sustenta. Aqui
        o perfil mantido continua sustentando o contrato, então a guarda não se
        aplica. O contrato aponta para a **contraparte**, nunca para o perfil.
        """
        perfil.status = StatusSolicitacao.CANCELADA
        perfil.motivo_cancelamento = MOTIVO.format(mantido=mantido.pk)
        perfil.data_cancelamento = timezone.now()
        # `cancelada_por` fica nulo: quem cancelou foi a manutenção, não uma pessoa.
        perfil.save()
        registrar(
            acao=Acao.TRANSICAO_ESTADO,
            descricao=(
                f"Perfil #{perfil.pk} cancelado como duplicado do #{mantido.pk} "
                f"(limpeza de base, AGENTS.md D57)"
            ),
            objeto=perfil,
        )

    def _resumo(self, duplicados, cancelados, filas_a_conferir, *, aplicar: bool) -> None:
        contrapartes = len(duplicados)
        plural = "s" if contrapartes != 1 else ""

        if filas_a_conferir:
            self.stdout.write(
                self.style.WARNING("\nHabilitações que continuam na fila, para conferir à mão:")
            )
            for perfil_pk, habilitacao in filas_a_conferir:
                self.stdout.write(
                    f"  habilitação #{habilitacao.pk} ({habilitacao.get_status_display()}), "
                    f"do perfil #{perfil_pk}"
                )
            self.stdout.write(
                "  As filas de compliance e de crédito leem a habilitação, não o perfil: "
                "cancelar o cadastro não tira a contraparte de lá. O comando não decide "
                "parecer, então isto fica para a área."
            )

        if aplicar:
            self.stdout.write(
                self.style.SUCCESS(
                    f"\n{contrapartes} contraparte{plural} com duplicata, "
                    f"{cancelados} perfil(is) cancelado(s)."
                )
            )
        else:
            self.stdout.write(
                self.style.WARNING(
                    f"\n{contrapartes} contraparte{plural} com duplicata, "
                    f"{cancelados} perfil(is) seria(m) cancelado(s). "
                    "Nada foi gravado: rode com --aplicar."
                )
            )
