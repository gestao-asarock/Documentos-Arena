"""
A solicitação vira **perfil**: só o que é da pessoa (AGENTS.md D29).

Evento, data, horário, valor e tipo de operação passam para o contrato. Era esse
acoplamento que prendia toda a validação da contraparte a um único contrato.
"""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("solicitacoes", "0003_cancelamento"),
    ]

    operations = [
        migrations.RemoveField(model_name="solicitacao", name="descricao"),
        migrations.RemoveField(model_name="solicitacao", name="data_evento"),
        migrations.RemoveField(model_name="solicitacao", name="horario_evento"),
        migrations.RemoveField(model_name="solicitacao", name="valor"),
        migrations.RemoveField(model_name="solicitacao", name="tipo_operacao"),
        migrations.AlterField(
            model_name="solicitacao",
            name="status",
            field=models.CharField(
                choices=[
                    ("rascunho", "Rascunho"),
                    ("em_habilitacao", "Perfil em validação"),
                    ("pronta_para_contrato", "Perfil validado"),
                    ("cancelada", "Cancelado"),
                ],
                default="rascunho",
                max_length=32,
            ),
        ),
        migrations.AlterModelOptions(
            name="solicitacao",
            options={
                "ordering": ("-data_criacao",),
                "verbose_name": "solicitação",
                "verbose_name_plural": "solicitações",
            },
        ),
    ]
