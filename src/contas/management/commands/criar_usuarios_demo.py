"""
Cria um usuário por papel, para testar o fluxo em desenvolvimento.

Recusa rodar com DEBUG=False: são contas de senha conhecida, que não podem
existir em produção (AGENTS.md §6).

    python manage.py criar_usuarios_demo
    python manage.py criar_usuarios_demo --senha outra-senha
"""

from django.conf import settings
from django.contrib.auth.models import Group
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from contas.models import Papel, Usuario

SENHA_PADRAO = "arena-demo-2026"

USUARIOS = [
    ("crm.demo", "Camila", "CRM", Papel.CRM),
    ("compliance.demo", "Caio", "Compliance", Papel.COMPLIANCE),
    ("juridico.demo", "Júlia", "Jurídico", Papel.JURIDICO),
    ("clube.demo", "Cláudio", "Clube", Papel.CLUBE),
]


class Command(BaseCommand):
    help = "Cria usuários de demonstração, um por papel (apenas com DEBUG=True)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--senha",
            default=SENHA_PADRAO,
            help=f"Senha dos usuários criados. Padrão: {SENHA_PADRAO}",
        )

    @transaction.atomic
    def handle(self, *args, **opcoes):
        if not settings.DEBUG:
            raise CommandError(
                "Este comando cria contas com senha conhecida e só roda com DEBUG=True. "
                "Em produção, crie os usuários pelo Admin."
            )

        senha = opcoes["senha"]
        for username, nome, sobrenome, papel in USUARIOS:
            usuario, criado = Usuario.objects.get_or_create(
                username=username,
                defaults={"first_name": nome, "last_name": sobrenome},
            )
            usuario.set_password(senha)
            # Acesso ao Admin fica com o superusuário; estes usam só as telas.
            usuario.is_staff = False
            usuario.save()

            grupo = Group.objects.get(name=papel)
            usuario.groups.set([grupo])

            estado = "criado" if criado else "atualizado"
            self.stdout.write(f"  {username:<18} papel: {papel:<12} ({estado})")

        self.stdout.write(self.style.SUCCESS(f"\n{len(USUARIOS)} usuários prontos. Senha: {senha}"))
        self.stdout.write("Entre em /contas/login/ com qualquer um deles.")
