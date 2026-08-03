"""
O perfil deixa de conhecer valor e crédito (AGENTS.md D29, D30).

Crédito depende do valor da operação, então saiu da validação do perfil. Assim o
mesmo perfil serve a vários contratos, que é o ponto da mudança.
"""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("contrapartes", "0005_arquivo_com_nome_nao_adivinhavel"),
    ]

    operations = [
        migrations.RemoveField(model_name="habilitacao", name="exige_credito"),
        migrations.AlterField(
            model_name="habilitacao",
            name="status",
            field=models.CharField(
                choices=[
                    ("aguardando_documentos", "Aguardando documentos"),
                    ("em_analise_documental", "Em análise documental"),
                    ("com_pendencia", "Com pendência"),
                    ("em_compliance", "Em análise de compliance"),
                    ("habilitada", "Perfil validado"),
                    ("recusada", "Recusado"),
                ],
                default="aguardando_documentos",
                max_length=32,
            ),
        ),
    ]
