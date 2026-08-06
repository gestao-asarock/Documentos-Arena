"""
Código público da contraparte (AGENTS.md D59).

Identificador estável derivado do CPF/CNPJ, para aparecer na tela no lugar de um
número sequencial. **Não é anonimização**: quem vê dois registros com o mesmo
código sabe que são a mesma pessoa, que é justamente a propriedade desejada.

O que ele evita é o caminho de volta. Hash puro do CPF não serviria: o espaço de
CPF válido é da ordem de 10^9, e uma tabela pré-calculada o reverte em segundos.
Com **HMAC e chave secreta** essa tabela não existe sem a chave. A chave mora no
`.env` (`HASH_KEY`), entra no backup e **nunca rotaciona**: girá-la trocaria o
código de todo mundo. Como o valor fica **gravado** no banco, perder a chave
custa só a capacidade de recalcular, não os códigos já emitidos.
"""

import hmac
from hashlib import sha256

from django.conf import settings

#: Base32 de Crockford: sem I, L, O e U. Os três primeiros se confundem com 1 e
#: 0 em leitura e ditado, e o U sai para não formar palavra indesejada por acaso.
ALFABETO = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"

#: Doze caracteres, cinco bits cada: 60 bits, 1,2 x 10^18 valores. Com cem mil
#: contrapartes a chance de colisão fica na casa de 10^-9, e ainda assim ela
#: seria detectada pelo `unique=True` da coluna, nunca silenciosa. Oito
#: caracteres já dariam colisão perceptível; dezesseis ninguém dita ao telefone.
CARACTERES = 12
BITS = CARACTERES * 5

#: Grupos de quatro na exibição, como `K7M4-2QX9-BT5R`. O hífen não é guardado.
TAMANHO_DO_GRUPO = 4


def gerar_codigo(documento: str) -> str:
    """Código determinístico para este CPF/CNPJ. Mesmo documento, mesmo código.

    Normaliza para dígitos aqui dentro em vez de reaproveitar
    `contrapartes.models.apenas_digitos`: `models` importa este módulo, e o
    contrário fecharia um ciclo. São duas linhas, e o preço de errar é gerar
    código diferente para o mesmo documento por causa de um ponto.
    """
    digitos = "".join(c for c in (documento or "") if c.isdigit())
    if not digitos:
        raise ValueError("Não há CPF/CNPJ para derivar o código.")

    assinatura = hmac.new(
        settings.HASH_KEY.encode("utf-8"), digitos.encode("utf-8"), sha256
    ).digest()

    # Os 60 bits mais significativos do digest, escritos da direita para a
    # esquerda em blocos de cinco.
    valor = int.from_bytes(assinatura, "big") >> (len(assinatura) * 8 - BITS)
    caracteres = []
    for _ in range(CARACTERES):
        caracteres.append(ALFABETO[valor & 0b11111])
        valor >>= 5
    return "".join(reversed(caracteres))


def normalizar_codigo(termo: str) -> str:
    """O que a pessoa digitou, pronto para comparar com a coluna. Vazio se não for código.

    Aceita com hífen, com espaço e em minúscula: o código circula por telefone e
    por e-mail, e exigir a forma exata faria a busca falhar justo para quem só
    tem ele na mão. O teste de tamanho é o que separa código de documento: CPF
    tem 11 dígitos e CNPJ tem 14, então nenhum dos dois passa por aqui.
    """
    limpo = "".join(c for c in (termo or "").upper() if c in ALFABETO)
    return limpo if len(limpo) == CARACTERES else ""


def formatar_codigo(codigo: str) -> str:
    """`K7M42QX9BT5R` vira `K7M4-2QX9-BT5R`. Só para a tela."""
    if not codigo:
        return "-"
    grupos = [codigo[i : i + TAMANHO_DO_GRUPO] for i in range(0, len(codigo), TAMANHO_DO_GRUPO)]
    return "-".join(grupos)


__all__ = ["ALFABETO", "CARACTERES", "formatar_codigo", "gerar_codigo", "normalizar_codigo"]
