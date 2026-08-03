from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("auditoria", "0002_initial"),
    ]

    operations = [
        migrations.AlterField(
            model_name="eventoauditoria",
            name="acao",
            field=models.CharField(
                choices=[
                    ("criacao", "Criação"),
                    ("enquadramento", "Enquadramento"),
                    ("envio_documento", "Envio de documento"),
                    ("exclusao_documento", "Exclusão de documento"),
                    ("analise_ia", "Análise por IA"),
                    ("consulta_compliance", "Consulta de compliance"),
                    ("transicao_estado", "Transição de estado"),
                    ("aprovacao", "Aprovação"),
                    ("reprovacao", "Reprovação"),
                    ("dispensa", "Dispensa (waiver)"),
                    ("download", "Download de documento"),
                ],
                max_length=32,
                verbose_name="ação",
            ),
        ),
    ]
