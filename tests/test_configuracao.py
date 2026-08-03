"""Testes de fumaça da configuração — garantem que o esqueleto está de pé."""

from django.conf import settings


def test_localizacao_brasileira():
    """AGENTS.md §3: interface e datas em padrão brasileiro."""
    assert settings.LANGUAGE_CODE == "pt-br"
    assert settings.TIME_ZONE == "America/Sao_Paulo"
    assert settings.USE_TZ is True


def test_provedores_externos_configuraveis():
    """AGENTS.md §5: integrações selecionadas por variável de ambiente."""
    assert settings.PROVEDOR_IA in {"gemini", "local", "fake"}
    assert settings.PROVEDOR_COMPLIANCE in {"trillia", "fake"}


def test_celery_configurado():
    from arena import celery_app

    assert celery_app.conf.broker_url
    assert celery_app.conf.timezone == settings.TIME_ZONE


def test_sem_segredo_no_repositorio():
    """AGENTS.md §6: a chave real vem do .env, nunca do código versionado."""
    assert settings.SECRET_KEY
    assert "troque-esta-chave" not in settings.SECRET_KEY or settings.DEBUG
