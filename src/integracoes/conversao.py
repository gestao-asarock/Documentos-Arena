"""
Conversão de DOCX em PDF (AGENTS.md §7, D33).

O Termo de Adesão chega em Word e precisa virar PDF para a assinatura. Não existe
conversão fiel em Python puro — e num contrato perder formatação é inaceitável —,
então usamos o **LibreOffice em modo headless**, que é o padrão para isso e roda
no container Linux.

Quando o LibreOffice não estiver disponível (Windows de desenvolvimento, por
exemplo), a conversão falha de forma explícita: `ConversaoIndisponivel`. Quem
chama decide o que mostrar — nunca entregue um arquivo dizendo que é PDF sem ser.
"""

import logging
import shutil
import subprocess
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)

#: Nomes do executável, conforme a instalação.
EXECUTAVEIS = ("soffice", "libreoffice")

TIMEOUT_SEGUNDOS = 120


class ConversaoIndisponivel(Exception):
    """LibreOffice não instalado, ou a conversão falhou."""


def executavel_disponivel() -> str | None:
    for nome in EXECUTAVEIS:
        caminho = shutil.which(nome)
        if caminho:
            return caminho
    return None


def converter_docx_em_pdf(conteudo: bytes, *, nome: str = "documento.docx") -> bytes:
    """Converte o DOCX recebido e devolve os bytes do PDF.

    Trabalha em diretório temporário próprio: o LibreOffice escreve o resultado
    ao lado do arquivo de entrada, e não queremos isso no storage.
    """
    programa = executavel_disponivel()
    if programa is None:
        raise ConversaoIndisponivel(
            "LibreOffice não está instalado neste ambiente. "
            "Em produção ele vem na imagem; localmente, envie o PDF direto."
        )

    with tempfile.TemporaryDirectory() as pasta:
        entrada = Path(pasta) / Path(nome).name
        entrada.write_bytes(conteudo)

        try:
            subprocess.run(
                [
                    programa,
                    "--headless",
                    # Perfil próprio: sem isto, instâncias simultâneas brigam
                    # pelo mesmo diretório de usuário e uma delas trava.
                    f"-env:UserInstallation=file://{pasta}/perfil",
                    "--convert-to",
                    "pdf",
                    "--outdir",
                    pasta,
                    str(entrada),
                ],
                check=True,
                capture_output=True,
                timeout=TIMEOUT_SEGUNDOS,
            )
        except subprocess.TimeoutExpired as erro:
            raise ConversaoIndisponivel("A conversão demorou demais e foi interrompida.") from erro
        except subprocess.CalledProcessError as erro:
            # Sem o conteúdo do documento no log (AGENTS.md §6).
            logger.warning("LibreOffice falhou ao converter (código %s).", erro.returncode)
            raise ConversaoIndisponivel("Não foi possível converter este arquivo.") from erro

        gerado = Path(pasta) / (entrada.stem + ".pdf")
        if not gerado.exists():
            raise ConversaoIndisponivel("A conversão não produziu um PDF.")
        return gerado.read_bytes()
