"""
O crédito volta para a esteira do perfil (AGENTS.md D30).

A análise da pessoa — score, restrições, protestos — não depende de valor, e o
perfil não é validado sem ela.
"""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("contrapartes", "0006_perfil_sem_credito"),
    ]

    operations = [
        migrations.AlterField(
            model_name="habilitacao",
            name="status",
            field=models.CharField(
                choices=[
                    ("aguardando_documentos", "Aguardando documentos"),
                    ("em_analise_documental", "Em análise documental"),
                    ("com_pendencia", "Com pendência"),
                    ("em_compliance", "Em análise de compliance"),
                    ("em_credito", "Em análise de crédito"),
                    ("habilitada", "Perfil validado"),
                    ("recusada", "Recusado"),
                ],
                default="aguardando_documentos",
                max_length=32,
            ),
        ),
    ]
