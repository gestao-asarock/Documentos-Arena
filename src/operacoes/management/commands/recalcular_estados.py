"""
Recalcula o estado de contratos e perfis a partir do que existe no banco.

O estado é gravado e só muda quando algo acontece — um envio, uma decisão. Ao
mudar uma regra de fluxo, registros parados ficam com o estado antigo e a tela
passa a mostrar duas informações conflitantes: o status gravado e a situação
calculada na hora.

Este comando reaplica as regras atuais sobre o que já está no banco. Não decide
nada nem aprova nada: só recoloca cada registro no estado que as regras de hoje
determinam.

    python manage.py recalcular_estados
    python manage.py recalcular_estados --simular   # mostra sem gravar
"""

from django.core.management.base import BaseCommand

from contrapartes.models import Habilitacao, StatusHabilitacao
from documentos.models import StatusDocumento
from operacoes.estados import ESTADOS_TERMINAIS
from operacoes.models import Operacao
from operacoes.servicos import avancar


class Command(BaseCommand):
    help = "Reaplica as regras de fluxo sobre contratos e perfis já existentes."

    def add_arguments(self, parser):
        parser.add_argument(
            "--simular",
            action="store_true",
            help="Mostra o que mudaria, sem gravar nada.",
        )

    def handle(self, *args, **opcoes):
        simular = opcoes["simular"]
        mudancas = 0

        self.stdout.write("Contratos:")
        for operacao in Operacao.objects.exclude(status__in=ESTADOS_TERMINAIS):
            anterior = operacao.status
            if simular:
                # Recalcula em memória, sem salvar.
                situacao = operacao.situacao_documental()
                esperado = self._estado_esperado(operacao, situacao)
            else:
                avancar(operacao)
                operacao.refresh_from_db()
                esperado = operacao.status

            if esperado != anterior:
                mudancas += 1
                self.stdout.write(f"  #{operacao.pk}: {anterior} → {esperado}")

        self.stdout.write("\nPerfis:")
        for habilitacao in Habilitacao.objects.exclude(
            status__in=[StatusHabilitacao.HABILITADA, StatusHabilitacao.RECUSADA]
        ):
            esperado = self._estado_do_perfil(habilitacao)
            if esperado and esperado != habilitacao.status:
                mudancas += 1
                self.stdout.write(f"  #{habilitacao.pk}: {habilitacao.status} → {esperado}")
                if not simular:
                    habilitacao.status = esperado
                    habilitacao.save()

        if mudancas == 0:
            self.stdout.write(self.style.SUCCESS("\nNada a corrigir: tudo já reflete as regras."))
        elif simular:
            self.stdout.write(
                self.style.WARNING(f"\n{mudancas} registro(s) mudariam. Rode sem --simular.")
            )
        else:
            self.stdout.write(self.style.SUCCESS(f"\n{mudancas} registro(s) atualizados."))

    def _estado_esperado(self, operacao, situacao):
        """Só para a simulação: o mesmo raciocínio de `avancar`, sem gravar."""
        from operacoes.estados import Etapa, StatusOperacao

        if situacao["faltando"] or situacao["com_problema"]:
            return StatusOperacao.AGUARDANDO_DOCUMENTOS

        proxima = operacao.etapa_atual
        if proxima is None:
            return StatusOperacao.CONCLUIDA
        if proxima.etapa == Etapa.ASSINATURAS:
            return StatusOperacao.AGUARDANDO_ASSINATURA
        if proxima.etapa == Etapa.RISCO_CREDITO:
            return StatusOperacao.EM_CREDITO
        return StatusOperacao.EM_APROVACAO

    def _estado_do_perfil(self, habilitacao):
        """O perfil segue o dossiê: sem documento aprovado, não avança."""
        contraparte = habilitacao.contraparte
        documentos = contraparte.documentos_cadastrais.all()

        if any(d.status == StatusDocumento.REJEITADO for d in documentos):
            return StatusHabilitacao.COM_PENDENCIA
        if contraparte.kit_completo():
            # Não force para compliance quem já passou dele.
            if habilitacao.status in {
                StatusHabilitacao.EM_COMPLIANCE,
                StatusHabilitacao.EM_CREDITO,
            }:
                return habilitacao.status
            return StatusHabilitacao.EM_COMPLIANCE
        if any(
            d.status in {StatusDocumento.ENVIADO, StatusDocumento.PROCESSANDO} for d in documentos
        ):
            return StatusHabilitacao.EM_ANALISE_DOCUMENTAL
        return StatusHabilitacao.AGUARDANDO_DOCUMENTOS
