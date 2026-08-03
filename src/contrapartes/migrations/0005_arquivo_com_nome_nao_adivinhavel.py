"""
Nome de arquivo não adivinhável (AGENTS.md §5.4).

Guardar o nome original no disco expõe o titular pela própria URL. O nome que o
usuário enviou continua no banco, para exibição.
"""

import contrapartes.models
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("contrapartes", "0004_endereco_estruturado_e_arquivos"),
    ]

    operations = [
        migrations.AlterField(
            model_name="arquivodocumento",
            name="arquivo",
            field=models.FileField(upload_to=contrapartes.models.caminho_do_arquivo),
        ),
        migrations.AlterField(
            model_name="arquivodocumento",
            name="nome_original",
            field=models.CharField(
                blank=True,
                help_text="Nome que o usuário enviou, só para exibição.",
                max_length=255,
            ),
        ),
    ]
