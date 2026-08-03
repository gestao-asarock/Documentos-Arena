"""Comando de usuários de demonstração (AGENTS.md §6)."""

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import override_settings

from contas.models import Papel, Usuario

pytestmark = pytest.mark.django_db


@override_settings(DEBUG=True)
def test_cria_um_usuario_por_papel():
    call_command("criar_usuarios_demo")

    for papel in (Papel.CRM, Papel.COMPLIANCE, Papel.JURIDICO, Papel.CLUBE):
        usuario = Usuario.objects.get(username=f"{papel}.demo")
        assert usuario.tem_papel(papel)
        assert not usuario.is_staff


@override_settings(DEBUG=True)
def test_rodar_duas_vezes_nao_duplica():
    call_command("criar_usuarios_demo")
    call_command("criar_usuarios_demo")

    assert Usuario.objects.filter(username__endswith=".demo").count() == 4


@override_settings(DEBUG=False)
def test_recusa_rodar_em_producao():
    """Conta com senha conhecida não pode existir em produção."""
    with pytest.raises(CommandError):
        call_command("criar_usuarios_demo")

    assert not Usuario.objects.filter(username__endswith=".demo").exists()
