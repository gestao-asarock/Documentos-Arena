"""
Validação de arquivo enviado (AGENTS.md §5.4, D18).

Ponto único: PDF, JPG e PNG, até 25 MB. Nenhuma tela define o seu próprio limite.
Extensão é sugestão do usuário — o que vale é a assinatura dos primeiros bytes.
"""

from django.core.exceptions import ValidationError

TAMANHO_MAXIMO_MB = 25
TAMANHO_MAXIMO_BYTES = TAMANHO_MAXIMO_MB * 1024 * 1024

EXTENSOES_ACEITAS = (".pdf", ".jpg", ".jpeg", ".png")

#: Assinatura (magic number) do início do arquivo → formato.
ASSINATURAS = {
    b"%PDF": "pdf",
    b"\xff\xd8\xff": "jpg",
    b"\x89PNG\r\n\x1a\n": "png",
}

#: Aceito pelo atributo `accept` do campo de upload, no navegador.
ACCEPT_HTML = ".pdf,.jpg,.jpeg,.png"


def validar_extensao(arquivo) -> None:
    nome = (getattr(arquivo, "name", "") or "").lower()
    if not nome.endswith(EXTENSOES_ACEITAS):
        raise ValidationError("Formato não aceito. Envie PDF, JPG ou PNG.")


def validar_tamanho(arquivo) -> None:
    tamanho = getattr(arquivo, "size", 0) or 0
    if tamanho > TAMANHO_MAXIMO_BYTES:
        atual = tamanho / (1024 * 1024)
        raise ValidationError(
            f"Arquivo de {atual:.1f} MB excede o limite de {TAMANHO_MAXIMO_MB} MB."
        )
    if tamanho == 0:
        raise ValidationError("O arquivo está vazio.")


def validar_conteudo(arquivo) -> str:
    """Confere a assinatura real do arquivo e devolve o formato detectado.

    Renomear .exe para .pdf não engana: o conteúdo é lido, não o nome.
    """
    posicao = arquivo.tell() if hasattr(arquivo, "tell") else 0
    arquivo.seek(0)
    inicio = arquivo.read(8)
    arquivo.seek(posicao)

    for assinatura, formato in ASSINATURAS.items():
        if inicio.startswith(assinatura):
            return formato

    raise ValidationError("O conteúdo do arquivo não corresponde a um PDF, JPG ou PNG válido.")


def validar_documento(arquivo) -> str:
    """Todas as validações, na ordem barata → cara. Devolve o formato detectado."""
    validar_extensao(arquivo)
    validar_tamanho(arquivo)
    return validar_conteudo(arquivo)
