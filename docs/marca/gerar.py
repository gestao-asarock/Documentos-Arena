"""
Gera `src/static/img/marca.png` e `favicon.ico` a partir de `brasao-original.jpg`.

Roda uma vez, à mão, e só precisa rodar de novo se o arquivo original mudar:

    python docs/marca/gerar.py

**O original é um JPEG, não um PNG.** O "quadriculado de transparência" que
aparece nele são pixels de verdade — cinza #DCDCDC alternando com branco.
Aplicado direto no cabeçalho ou na aba do navegador, vira um tabuleiro cinza.

Recortar o fundo a partir das bordas não basta: entre os braços da âncora há
regiões de xadrez fechadas, que um balde de tinta nunca alcança. E não dá para
apagar "tudo que é claro", porque a bandeira e a corda do brasão também são
brancas.

O que distingue o xadrez é ser xadrez: metade cinza, metade branco. Então
separamos as regiões contíguas de pixels claros e neutros e descartamos as que
misturam os dois tons em proporção de tabuleiro. Uma listra branca da bandeira é
quase toda branca e sobrevive; um trecho de fundo é meio a meio e cai.

Requer Pillow, que **não** está nos requirements: é ferramenta de uma vez só, e
não vale virar dependência do projeto por causa dela. Se precisar rodar de novo,
`pip install pillow` no venv e desinstale depois, se quiser.
"""

from pathlib import Path

from PIL import Image

RAIZ = Path.cwd()
if not (RAIZ / "manage.py").exists():
    raise SystemExit("Rode a partir da raiz do repositório.")

ORIGEM = RAIZ / "docs/marca/brasao-original.jpg"
DESTINO = RAIZ / "src/static/img"

#: Um pixel é "de fundo em potencial" se for claro e sem cor. Pega os dois tons
#: do xadrez sem encostar no vermelho nem no preto do brasão.
BRILHO_MINIMO = 195
NEUTRALIDADE_MAXIMA = 25
#: Abaixo disto, o pixel claro é o tom cinza do xadrez, não o branco da arte.
CINZA_MAXIMO = 238

DESTINO.mkdir(parents=True, exist_ok=True)

imagem = Image.open(ORIGEM).convert("RGB")
largura, altura = imagem.size
pixels = imagem.load()


def e_claro_e_neutro(x: int, y: int) -> bool:
    r, g, b = pixels[x, y]
    return min(r, g, b) > BRILHO_MINIMO and max(r, g, b) - min(r, g, b) < NEUTRALIDADE_MAXIMA


def regiao_a_partir_de(inicio: tuple[int, int], visitado: bytearray) -> list[tuple[int, int]]:
    """Todos os pixels claros e neutros ligados a este, em quatro direções."""
    regiao, pilha = [], [inicio]
    visitado[inicio[1] * largura + inicio[0]] = 1
    while pilha:
        x, y = pilha.pop()
        regiao.append((x, y))
        for vx, vy in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
            if not (0 <= vx < largura and 0 <= vy < altura):
                continue
            if visitado[vy * largura + vx] or not e_claro_e_neutro(vx, vy):
                continue
            visitado[vy * largura + vx] = 1
            pilha.append((vx, vy))
    return regiao


def e_xadrez(regiao: list[tuple[int, int]]) -> bool:
    """Tabuleiro é meio a meio. Arte branca do brasão fica bem acima de 0,8."""
    brancos = sum(1 for x, y in regiao if pixels[x, y][0] >= CINZA_MAXIMO)
    return 0.2 < brancos / len(regiao) < 0.8


visitado = bytearray(largura * altura)
recortada = imagem.convert("RGBA")
finais = recortada.load()
fundo = 0

for x_inicial in range(largura):
    for y_inicial in range(altura):
        if visitado[y_inicial * largura + x_inicial] or not e_claro_e_neutro(x_inicial, y_inicial):
            continue

        regiao = regiao_a_partir_de((x_inicial, y_inicial), visitado)
        if not e_xadrez(regiao):
            continue

        for x, y in regiao:
            finais[x, y] = (0, 0, 0, 0)
            fundo += 1

# O JPEG tem margem sobrando: corta na caixa do que restou e centraliza num
# quadrado, para o favicon não sair esmagado nem torto.
recortada = recortada.crop(recortada.getbbox())
lado = max(recortada.size)
quadrada = Image.new("RGBA", (lado, lado), (0, 0, 0, 0))
quadrada.paste(recortada, ((lado - recortada.size[0]) // 2, (lado - recortada.size[1]) // 2))

quadrada.resize((512, 512), Image.LANCZOS).save(DESTINO / "marca.png")
quadrada.resize((256, 256), Image.LANCZOS).save(
    DESTINO / "favicon.ico", sizes=[(16, 16), (32, 32), (48, 48)]
)

print(f"fundo recortado: {fundo / (largura * altura):.1%} da imagem")
print(f"arte útil: {recortada.size} -> marca.png 512px, favicon.ico 16/32/48")
