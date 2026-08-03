import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("solicitacoes", "0002_alter_solicitacao_id"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="solicitacao",
            name="motivo_cancelamento",
            field=models.TextField(blank=True, verbose_name="motivo do cancelamento"),
        ),
        migrations.AddField(
            model_name="solicitacao",
            name="cancelada_por",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="solicitacoes_canceladas",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="solicitacao",
            name="data_cancelamento",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
