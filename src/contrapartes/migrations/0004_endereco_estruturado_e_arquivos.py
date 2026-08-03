import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("contrapartes", "0003_alter_habilitacao_id"),
        ("documentos", "0008_carga_subtipos_identificacao"),
    ]

    operations = [
        # Endereço estruturado no lugar de texto livre (AGENTS.md §4.6).
        migrations.RemoveField(model_name="contraparte", name="endereco"),
        migrations.AddField(
            model_name="contraparte",
            name="cep",
            field=models.CharField(blank=True, max_length=9, verbose_name="CEP"),
        ),
        migrations.AddField(
            model_name="contraparte",
            name="logradouro",
            field=models.CharField(blank=True, max_length=200),
        ),
        migrations.AddField(
            model_name="contraparte",
            name="numero",
            field=models.CharField(blank=True, max_length=20, verbose_name="número"),
        ),
        migrations.AddField(
            model_name="contraparte",
            name="complemento",
            field=models.CharField(blank=True, max_length=100),
        ),
        migrations.AddField(
            model_name="contraparte",
            name="bairro",
            field=models.CharField(blank=True, max_length=100),
        ),
        migrations.AddField(
            model_name="contraparte",
            name="cidade",
            field=models.CharField(blank=True, max_length=100),
        ),
        migrations.AddField(
            model_name="contraparte",
            name="uf",
            field=models.CharField(blank=True, max_length=2, verbose_name="UF"),
        ),
        # Um documento passa a ter vários arquivos: frente e verso, páginas.
        migrations.AddField(
            model_name="documentocadastral",
            name="subtipo",
            field=models.ForeignKey(
                blank=True,
                help_text="Qual documento é, dentro do tipo: RG, CNH, passaporte...",
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                to="documentos.subtipodocumento",
            ),
        ),
        migrations.CreateModel(
            name="ArquivoDocumento",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("arquivo", models.FileField(upload_to="cadastral/%Y/%m/")),
                ("nome_original", models.CharField(blank=True, max_length=255)),
                ("ordem", models.PositiveSmallIntegerField(default=0)),
                ("data_envio", models.DateTimeField(auto_now_add=True)),
                (
                    "documento",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="arquivos",
                        to="contrapartes.documentocadastral",
                    ),
                ),
            ],
            options={
                "verbose_name": "arquivo do documento",
                "verbose_name_plural": "arquivos do documento",
                "ordering": ("documento", "ordem"),
            },
        ),
        migrations.RemoveField(model_name="documentocadastral", name="arquivo"),
        migrations.RemoveField(model_name="documentocadastral", name="nome_original"),
    ]
