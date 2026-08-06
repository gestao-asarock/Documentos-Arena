"""
Registra que a conferência aceitou um documento fora do prazo (AGENTS.md D55).

O vencimento avisa, não barra: aprovar um comprovante antigo é decisão de quem
tria. Sem esta marca o dossiê devolvia o documento para "precisa de correção" logo
depois de aprovado, desfazendo em silêncio o parecer que acabara de ser dado.
"""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("contrapartes", "0009_contraparte_alterada_por_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="documentocadastral",
            name="prazo_dispensado",
            field=models.BooleanField(
                default=False,
                help_text=(
                    "Marcado quando a conferência aprova um documento que já estava "
                    "fora do prazo. O vencimento avisa; quem decide é o parecer humano."
                ),
                verbose_name="prazo dispensado na conferência",
            ),
        ),
    ]
