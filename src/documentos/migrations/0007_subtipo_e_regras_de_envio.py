import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("documentos", "0006_alter_exigenciacadastral_id"),
    ]

    operations = [
        migrations.AddField(
            model_name="tipodocumento",
            name="exige_data_emissao",
            field=models.BooleanField(
                default=True,
                help_text="Desmarque quando a emissão não define a validade — o RG, por exemplo.",
                verbose_name="exige data de emissão",
            ),
        ),
        migrations.AddField(
            model_name="tipodocumento",
            name="aceita_multiplos_arquivos",
            field=models.BooleanField(
                default=True,
                help_text="Frente e verso, páginas separadas, anexos do mesmo documento.",
                verbose_name="aceita vários arquivos",
            ),
        ),
        migrations.CreateModel(
            name="SubtipoDocumento",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("nome", models.CharField(max_length=80)),
                (
                    "tem_validade_propria",
                    models.BooleanField(
                        default=False,
                        help_text=(
                            "CNH e passaporte vencem; RG não. Define se pedimos a data de validade."
                        ),
                    ),
                ),
                ("ativo", models.BooleanField(default=True)),
                (
                    "tipo_documento",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="subtipos",
                        to="documentos.tipodocumento",
                    ),
                ),
            ],
            options={
                "verbose_name": "subtipo de documento",
                "verbose_name_plural": "subtipos de documento",
                "ordering": ("tipo_documento__nome", "nome"),
                "unique_together": {("tipo_documento", "nome")},
            },
        ),
    ]
