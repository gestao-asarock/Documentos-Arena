"""
Conferência documental (AGENTS.md §4.6).

O estado da habilitação é derivado do dossiê, nunca assumido.
"""

from datetime import timedelta

import pytest
from django.contrib.auth.models import Group
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from django.utils import timezone

from analise.servicos import aprovar_documento, fila_de_conferencia, rejeitar_documento
from contas.models import Papel, Usuario
from contrapartes.models import ArquivoDocumento, DocumentoCadastral, StatusHabilitacao
from documentos.models import StatusDocumento
from solicitacoes.models import Solicitacao
from solicitacoes.servicos import abrir_habilitacao, obter_ou_criar_contraparte

pytestmark = pytest.mark.django_db

PDF = b"%PDF-1.4 conteudo ficticio"


def _usuario(nome: str, papel: str) -> Usuario:
    usuario = Usuario.objects.create_user(username=nome, password="senha-de-teste")
    usuario.groups.add(Group.objects.get(name=papel))
    return usuario


@pytest.fixture
def clube():
    return _usuario("clube.conferencia", Papel.CLUBE)


@pytest.fixture
def compliance():
    return _usuario("compliance.conferencia", Papel.COMPLIANCE)


@pytest.fixture
def solicitacao(clube):
    contraparte, _ = obter_ou_criar_contraparte(
        documento="58974790890", dados={"nome": "Contratante Fictício"}
    )
    solicitacao = Solicitacao.objects.create(contraparte=contraparte, criada_por=clube)
    abrir_habilitacao(solicitacao, usuario=clube)
    return solicitacao


def _enviar(solicitacao, tipo, usuario):
    documento = DocumentoCadastral.objects.create(
        contraparte=solicitacao.contraparte, tipo=tipo, enviado_por=usuario
    )
    ArquivoDocumento.objects.create(
        documento=documento,
        arquivo=SimpleUploadedFile("documento.pdf", PDF),
        nome_original="documento.pdf",
    )
    return documento


# -- Acesso ------------------------------------------------------------------


def test_clube_nao_acessa_a_fila(client, clube):
    client.force_login(clube)

    assert client.get(reverse("analise:fila")).status_code == 403


def test_compliance_acessa_a_fila(client, compliance):
    client.force_login(compliance)

    assert client.get(reverse("analise:fila")).status_code == 200


def test_menu_mostra_a_fila_apenas_para_quem_confere(client, clube, compliance):
    client.force_login(compliance)
    assert reverse("analise:fila") in client.get(reverse("solicitacoes:lista")).content.decode()

    client.force_login(clube)
    assert reverse("analise:fila") not in client.get(reverse("solicitacoes:lista")).content.decode()


def test_fila_traz_os_mais_antigos_primeiro(solicitacao, clube):
    tipos = solicitacao.pendencias_cadastrais()
    primeiro = _enviar(solicitacao, tipos[0], clube)
    segundo = _enviar(solicitacao, tipos[1], clube)

    assert list(fila_de_conferencia()) == [primeiro, segundo]


def test_documento_aprovado_sai_da_fila(solicitacao, clube, compliance):
    documento = _enviar(solicitacao, solicitacao.pendencias_cadastrais()[0], clube)

    aprovar_documento(documento, usuario=compliance)

    assert documento not in fila_de_conferencia()


# -- Efeito no fluxo ---------------------------------------------------------


def test_kit_completo_leva_para_compliance(solicitacao, clube, compliance):
    """Todos os documentos aprovados → a contraparte segue para due diligence."""
    for tipo in list(solicitacao.pendencias_cadastrais()):
        documento = _enviar(solicitacao, tipo, clube)
        aprovar_documento(documento, usuario=compliance)

    solicitacao.habilitacao.refresh_from_db()

    assert solicitacao.kit_completo
    assert solicitacao.habilitacao.status == StatusHabilitacao.EM_COMPLIANCE


def test_kit_incompleto_nao_avanca(solicitacao, clube, compliance):
    documento = _enviar(solicitacao, solicitacao.pendencias_cadastrais()[0], clube)

    aprovar_documento(documento, usuario=compliance)
    solicitacao.habilitacao.refresh_from_db()

    assert solicitacao.habilitacao.status != StatusHabilitacao.EM_COMPLIANCE


def test_rejeicao_trava_o_fluxo_com_pendencia(solicitacao, clube, compliance):
    documento = _enviar(solicitacao, solicitacao.pendencias_cadastrais()[0], clube)

    rejeitar_documento(documento, usuario=compliance, motivo="Documento ilegível.")
    documento.refresh_from_db()
    solicitacao.habilitacao.refresh_from_db()

    assert documento.status == StatusDocumento.REJEITADO
    assert documento.observacao == "Documento ilegível."
    assert solicitacao.habilitacao.status == StatusHabilitacao.COM_PENDENCIA


def test_rejeicao_exige_motivo(solicitacao, clube, compliance):
    """Sem motivo o Clube não sabe o que corrigir (AGENTS.md §4.6)."""
    documento = _enviar(solicitacao, solicitacao.pendencias_cadastrais()[0], clube)

    with pytest.raises(ValueError):
        rejeitar_documento(documento, usuario=compliance, motivo="   ")


def test_clube_ve_o_motivo_da_rejeicao(client, solicitacao, clube, compliance):
    documento = _enviar(solicitacao, solicitacao.pendencias_cadastrais()[0], clube)
    rejeitar_documento(documento, usuario=compliance, motivo="Comprovante fora do prazo.")
    client.force_login(clube)

    corpo = client.get(reverse("solicitacoes:detalhe", args=[solicitacao.pk])).content.decode()

    assert "Comprovante fora do prazo." in corpo


def test_decisao_pela_tela_aprova(client, solicitacao, clube, compliance):
    documento = _enviar(solicitacao, solicitacao.pendencias_cadastrais()[0], clube)
    client.force_login(compliance)

    client.post(
        reverse("analise:decidir", args=[documento.pk]),
        {"acao": "aprovar", "observacao": "Confere com o formulário."},
    )
    documento.refresh_from_db()

    assert documento.status == StatusDocumento.APROVADO


def test_rejeicao_sem_motivo_pela_tela_nao_muda_nada(client, solicitacao, clube, compliance):
    documento = _enviar(solicitacao, solicitacao.pendencias_cadastrais()[0], clube)
    client.force_login(compliance)

    client.post(reverse("analise:decidir", args=[documento.pk]), {"acao": "rejeitar"})
    documento.refresh_from_db()

    assert documento.status == StatusDocumento.ENVIADO


# -- Documento fora do prazo (AGENTS.md D55) ---------------------------------


def _com_prazo(tipo, dias_validade=90):
    tipo.dias_validade = dias_validade
    tipo.save()
    return tipo


def _enviar_vencido(solicitacao, tipo, usuario, *, dias_de_idade=189):
    documento = _enviar(solicitacao, _com_prazo(tipo), usuario)
    documento.data_emissao = timezone.localdate() - timedelta(days=dias_de_idade)
    documento.save()
    return documento


def test_documento_vencido_ainda_nao_conferido_fica_em_analise(solicitacao, clube):
    """Antes da decisão, o prazo é aviso: quem tria é que diz se passa."""
    documento = _enviar_vencido(solicitacao, solicitacao.pendencias_cadastrais()[0], clube)

    kit = solicitacao.contraparte.situacao_do_kit()

    assert documento in kit["em_analise"]
    assert documento not in kit["com_problema"]


def test_aprovar_fora_do_prazo_vale_como_vigente(solicitacao, clube, compliance):
    """O parecer é que decide: aprovado fora do prazo continua aprovado."""
    documento = _enviar_vencido(solicitacao, solicitacao.pendencias_cadastrais()[0], clube)

    aprovar_documento(documento, usuario=compliance)
    documento.refresh_from_db()

    assert documento.esta_vencido
    assert documento.prazo_dispensado
    assert documento.esta_vigente


def test_documento_aceito_fora_do_prazo_sai_da_pendencia(client, solicitacao, clube, compliance):
    """O caso relatado: aprovar devolvia o documento para 'precisa de correção'."""
    tipo = solicitacao.pendencias_cadastrais()[0]
    documento = _enviar_vencido(solicitacao, tipo, clube)
    aprovar_documento(documento, usuario=compliance)

    kit = solicitacao.contraparte.situacao_do_kit()

    assert documento in kit["vigentes"]
    assert documento not in kit["com_problema"]
    assert tipo not in solicitacao.contraparte.pendencias_cadastrais()

    client.force_login(clube)
    corpo = client.get(reverse("solicitacoes:detalhe", args=[solicitacao.pk])).content.decode()
    assert "Precisa de correção" not in corpo


def test_kit_com_documento_aceito_fora_do_prazo_avanca(solicitacao, clube, compliance):
    for indice, tipo in enumerate(list(solicitacao.pendencias_cadastrais())):
        if indice == 0:
            documento = _enviar_vencido(solicitacao, tipo, clube)
        else:
            documento = _enviar(solicitacao, tipo, clube)
        aprovar_documento(documento, usuario=compliance)

    solicitacao.habilitacao.refresh_from_db()

    assert solicitacao.habilitacao.status == StatusHabilitacao.EM_COMPLIANCE


def test_documento_que_vence_depois_de_aprovado_volta_a_ser_pendencia(
    solicitacao, clube, compliance
):
    """A dispensa é da conferência daquele momento, não um passe permanente."""
    tipo = _com_prazo(solicitacao.pendencias_cadastrais()[0])
    documento = _enviar(solicitacao, tipo, clube)
    documento.data_emissao = timezone.localdate()
    documento.save()
    aprovar_documento(documento, usuario=compliance)

    documento.data_emissao = timezone.localdate() - timedelta(days=200)
    documento.save()

    assert not documento.esta_vigente
    assert tipo in solicitacao.contraparte.pendencias_cadastrais()


def test_rejeitar_desfaz_a_dispensa_de_prazo(solicitacao, clube, compliance):
    documento = _enviar_vencido(solicitacao, solicitacao.pendencias_cadastrais()[0], clube)
    aprovar_documento(documento, usuario=compliance)

    rejeitar_documento(documento, usuario=compliance, motivo="Preciso de um mais recente.")
    documento.refresh_from_db()

    assert not documento.prazo_dispensado
    assert not documento.esta_vigente


def test_conferencia_avisa_do_prazo_sem_barrar(client, solicitacao, clube, compliance):
    documento = _enviar_vencido(solicitacao, solicitacao.pendencias_cadastrais()[0], clube)
    client.force_login(compliance)

    corpo = client.get(reverse("analise:conferir", args=[documento.pk])).content.decode()

    assert "fora do prazo" in corpo
    assert "aprovar aceita o documento assim mesmo" in corpo.lower()
