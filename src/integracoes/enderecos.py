"""
Busca de endereço por CEP (AGENTS.md §7, D24).

Exceção consciente à regra "toda chamada externa vira task Celery": aqui o
usuário está esperando o preenchimento na tela, e a consulta é rápida e sem
persistência. Por isso: timeout curto, cache, e falha silenciosa — se o serviço
não responder, o usuário digita o endereço à mão e o cadastro segue.

Usa a stdlib de propósito, para não acrescentar dependência.
"""

import json
import logging
from urllib.error import URLError
from urllib.request import urlopen

from django.core.cache import cache

logger = logging.getLogger(__name__)

URL_VIACEP = "https://viacep.com.br/ws/{cep}/json/"
TIMEOUT_SEGUNDOS = 4
CACHE_SEGUNDOS = 60 * 60 * 24 * 30  # CEP praticamente não muda.


def normalizar_cep(cep: str) -> str:
    return "".join(c for c in (cep or "") if c.isdigit())


def buscar_por_cep(cep: str) -> dict | None:
    """Devolve os campos do endereço, ou None quando não há resposta útil.

    Nunca levanta exceção: endereço não encontrado é caso normal, não erro.
    """
    numero = normalizar_cep(cep)
    if len(numero) != 8:
        return None

    chave = f"cep:{numero}"
    if (guardado := cache.get(chave)) is not None:
        return guardado or None

    try:
        with urlopen(URL_VIACEP.format(cep=numero), timeout=TIMEOUT_SEGUNDOS) as resposta:
            dados = json.loads(resposta.read().decode("utf-8"))
    except (URLError, TimeoutError, ValueError, OSError):
        # Sem log do CEP: é dado pessoal do cadastro (AGENTS.md §6).
        logger.warning("Consulta de CEP indisponível.")
        return None

    if dados.get("erro"):
        cache.set(chave, {}, CACHE_SEGUNDOS)
        return None

    endereco = {
        "cep": dados.get("cep", "").replace("-", ""),
        "logradouro": dados.get("logradouro", ""),
        "bairro": dados.get("bairro", ""),
        "cidade": dados.get("localidade", ""),
        "uf": dados.get("uf", ""),
    }
    cache.set(chave, endereco, CACHE_SEGUNDOS)
    return endereco
