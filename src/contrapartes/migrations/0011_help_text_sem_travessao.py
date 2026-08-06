"""
Alinha o `help_text` que perdeu o travessão (AGENTS.md D49).

Mesma história da corretiva de `documentos`: o modelo mudou, a migration não.
Só metadado, sem SQL.
"""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("contrapartes", "0010_documento_prazo_dispensado"),
    ]

    operations = [
        migrations.AlterField(
            model_name="contraparte",
            name="campos_alterados",
            field=models.CharField(
                blank=True,
                help_text="O que mudou na última edição. Só rótulos, nunca o conteúdo.",
                max_length=255,
                verbose_name="campos alterados",
            ),
        ),
    ]
