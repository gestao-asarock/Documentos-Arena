"""
O contrato passa a carregar os dados do evento e os documentos do perfil
(AGENTS.md D29, D30).
"""

from django.db import migrations, models

STATUS = [
    ("rascunho", "Rascunho"),
    ("aguardando_documentos", "Aguardando documentos"),
    ("em_analise_documental", "Em análise documental"),
    ("em_credito", "Em análise de crédito"),
    ("em_aprovacao", "Em aprovação"),
    ("aguardando_assinatura", "Aguardando assinatura"),
    ("assinada", "Assinada"),
    ("concluida", "Concluída"),
    ("reprovada", "Reprovada"),
    ("dispensada", "Dispensada (waiver)"),
    ("cancelada", "Cancelada"),
]


class Migration(migrations.Migration):
    dependencies = [
        ("operacoes", "0004_cancelamento"),
        ("contrapartes", "0006_perfil_sem_credito"),
    ]

    operations = [
        migrations.RemoveField(model_name="operacao", name="solicitacao"),
        migrations.AddField(
            model_name="operacao",
            name="data_evento",
            field=models.DateField(blank=True, null=True, verbose_name="data do evento"),
        ),
        migrations.AddField(
            model_name="operacao",
            name="horario_evento",
            field=models.TimeField(blank=True, null=True, verbose_name="horário"),
        ),
        migrations.AddField(
            model_name="operacao",
            name="documentos",
            field=models.ManyToManyField(
                blank=True,
                related_name="operacoes",
                to="contrapartes.documentocadastral",
                verbose_name="documentos complementares",
            ),
        ),
        migrations.AlterField(
            model_name="operacao",
            name="status",
            field=models.CharField(choices=STATUS, default="rascunho", max_length=32),
        ),
    ]
