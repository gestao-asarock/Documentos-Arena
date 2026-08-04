"""
Guarda o PDF gerado a partir de um DOCX (AGENTS.md D33).

A conversão acontece uma vez, quando o contrato é liberado para assinatura, e o
resultado fica junto do arquivo original — o Clube baixa sempre o mesmo PDF.
"""

import contrapartes.models
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("contrapartes", "0007_perfil_com_credito"),
    ]

    operations = [
        migrations.AddField(
            model_name="arquivodocumento",
            name="pdf_convertido",
            field=models.FileField(
                blank=True,
                help_text=(
                    "Versão em PDF de um DOCX, gerada para a assinatura (AGENTS.md D33)."
                ),
                upload_to=contrapartes.models.caminho_do_arquivo,
                verbose_name="PDF convertido",
            ),
        ),
    ]
