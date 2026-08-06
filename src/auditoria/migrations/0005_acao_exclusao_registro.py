"""
Nova ação de auditoria: exclusão de registro (AGENTS.md D58).

Escrita à mão. Só mexe no estado do Django: `choices` não vira nada no banco,
então não há alteração de esquema nem risco de dado.
"""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("auditoria", "0004_alter_eventoauditoria_acao"),
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
                    ("exclusao_registro", "Exclusão de registro"),
                    ("alteracao_cadastral", "Alteração cadastral"),
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
