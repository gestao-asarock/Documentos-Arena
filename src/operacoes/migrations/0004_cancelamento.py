import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("operacoes", "0003_operacao_nasce_da_solicitacao"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="operacao",
            name="motivo_cancelamento",
            field=models.TextField(blank=True, verbose_name="motivo do cancelamento"),
        ),
        migrations.AddField(
            model_name="operacao",
            name="cancelada_por",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="operacoes_canceladas",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="operacao",
            name="data_cancelamento",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name="operacao",
            name="status",
            field=models.CharField(
                choices=[
                    ("rascunho", "Rascunho"),
                    ("aguardando_documentos", "Aguardando documentos"),
                    ("em_aprovacao", "Em aprovação"),
                    ("aguardando_assinatura", "Aguardando assinatura"),
                    ("assinada", "Assinada"),
                    ("concluida", "Concluída"),
                    ("reprovada", "Reprovada"),
                    ("dispensada", "Dispensada (waiver)"),
                    ("cancelada", "Cancelada"),
                ],
                default="rascunho",
                max_length=32,
            ),
        ),
    ]
