"""
Validação de arquivo enviado (AGENTS.md §5.4, D18).

Ponto único: PDF, JPG e PNG, até 25 MB. Nenhuma tela define o seu próprio limite.
Extensão é sugestão do usuário — o que vale é a assinatura dos primeiros bytes.
"""

from django.core.exceptions import ValidationError

TAMANHO_MAXIMO_MB = 25
TAMANHO_MAXIMO_BYTES = TAMANHO_MAXIMO_MB * 1024 * 1024

EXTENSOES_ACEITAS = (".pdf", ".jpg", ".jpeg", ".png")

#: Documento de contrato aceita DOCX: o Termo de Adesão é preenchido em Word pelo
#: Clube (AGENTS.md D31). Kit cadastral não — ninguém tem RG em Word (D32).
EXTENSOES_COM_DOCX = EXTENSOES_ACEITAS + (".docx",)

#: Assinatura (magic number) do início do arquivo → formato.
ASSINATURAS = {
    b"%PDF": "pdf",
    b"\xff\xd8\xff": "jpg",
    b"\x89PNG\r\n\x1a\n": "png",
    # DOCX é um zip; o conteúdo é conferido depois, em `_parece_docx`.
    b"PK\x03\x04": "docx",
}

#: Aceito pelo atributo `accept` do campo de upload, no navegador.
ACCEPT_HTML = ".pdf,.jpg,.jpeg,.png"
ACCEPT_HTML_COM_DOCX = ACCEPT_HTML + ",.docx"
ACCEPT_HTML_SO_PDF = ".pdf"


def validar_extensao(arquivo, *, aceitar_docx: bool = False) -> None:
    nome = (getattr(arquivo, "name", "") or "").lower()
    aceitas = EXTENSOES_COM_DOCX if aceitar_docx else EXTENSOES_ACEITAS
    if not nome.endswith(aceitas):
        formatos = "PDF, JPG, PNG ou DOCX" if aceitar_docx else "PDF, JPG ou PNG"
        raise ValidationError(f"Formato não aceito. Envie {formatos}.")


def validar_tamanho(arquivo) -> None:
    tamanho = getattr(arquivo, "size", 0) or 0
    if tamanho > TAMANHO_MAXIMO_BYTES:
        atual = tamanho / (1024 * 1024)
        raise ValidationError(
            f"Arquivo de {atual:.1f} MB excede o limite de {TAMANHO_MAXIMO_MB} MB."
        )
    if tamanho == 0:
        raise ValidationError("O arquivo está vazio.")


def _parece_docx(arquivo) -> bool:
    """Zip com `word/document.xml` dentro — não basta ser zip."""
    import zipfile

    posicao = arquivo.tell() if hasattr(arquivo, "tell") else 0
    arquivo.seek(0)
    try:
        with zipfile.ZipFile(arquivo) as pacote:
            return "word/document.xml" in pacote.namelist()
    except (zipfile.BadZipFile, OSError):
        return False
    finally:
        arquivo.seek(posicao)


def validar_conteudo(arquivo, *, aceitar_docx: bool = False) -> str:
    """Confere a assinatura real do arquivo e devolve o formato detectado.

    Renomear .exe para .pdf não engana: o conteúdo é lido, não o nome.
    """
    posicao = arquivo.tell() if hasattr(arquivo, "tell") else 0
    arquivo.seek(0)
    inicio = arquivo.read(8)
    arquivo.seek(posicao)

    for assinatura, formato in ASSINATURAS.items():
        if not inicio.startswith(assinatura):
            continue
        if formato == "docx":
            # Todo zip começa com PK: só é DOCX se tiver o documento do Word.
            if aceitar_docx and _parece_docx(arquivo):
                return "docx"
            continue
        return formato

    formatos = "PDF, JPG, PNG ou DOCX" if aceitar_docx else "PDF, JPG ou PNG"
    raise ValidationError(f"O conteúdo do arquivo não corresponde a um {formatos} válido.")


def validar_documento(arquivo, *, aceitar_docx: bool = False) -> str:
    """Todas as validações, na ordem barata → cara. Devolve o formato detectado."""
    validar_extensao(arquivo, aceitar_docx=aceitar_docx)
    validar_tamanho(arquivo)
    return validar_conteudo(arquivo, aceitar_docx=aceitar_docx)


def validar_pdf(arquivo) -> str:
    """Só PDF, mesmo limite de tamanho.

    O relatório de due diligence é documento fechado, não print de tela: aceitar
    imagem aqui só produziria evidência solta.
    """
    nome = (getattr(arquivo, "name", "") or "").lower()
    if not nome.endswith(".pdf"):
        raise ValidationError("Formato não aceito. Envie PDF.")
    validar_tamanho(arquivo)
    if validar_conteudo(arquivo) != "pdf":
        raise ValidationError("O conteúdo do arquivo não corresponde a um PDF válido.")
    return "pdf"
