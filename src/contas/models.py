"""
Usuários e papéis (AGENTS.md §4.2).

Os papéis são Groups do Django — as constantes abaixo apenas nomeiam esses grupos,
para que nenhum lugar do código escreva a string solta.
"""

from django.contrib.auth.models import AbstractUser
from django.db import models


class Papel(models.TextChoices):
    ADMINISTRADOR = "administrador", "Administrador"
    CRM = "crm", "CRM / Triagem"
    COMPLIANCE = "compliance", "Compliance"
    JURIDICO = "juridico", "Jurídico"
    CLUBE = "clube", "Clube"


#: Papéis internos da ASAROCK. O papel `clube` é externo e recebe tratamento
#: restritivo em toda queryset (AGENTS.md §4.2).
PAPEIS_INTERNOS = frozenset({Papel.ADMINISTRADOR, Papel.CRM, Papel.COMPLIANCE, Papel.JURIDICO})


class Usuario(AbstractUser):
    """Usuário do sistema.

    Existe desde o início mesmo sem campos próprios: trocar o modelo de usuário
    depois da primeira migração é inviável na prática.
    """

    class Meta:
        verbose_name = "usuário"
        verbose_name_plural = "usuários"

    def tem_papel(self, papel: str) -> bool:
        return self.groups.filter(name=papel).exists()

    @property
    def eh_do_clube(self) -> bool:
        """Usuário externo: enxerga apenas o que seu time criou."""
        return self.tem_papel(Papel.CLUBE)

    @property
    def eh_interno(self) -> bool:
        return self.is_superuser or self.groups.filter(name__in=PAPEIS_INTERNOS).exists()

    def __str__(self) -> str:
        nome = self.get_full_name()
        return nome or self.get_username()
