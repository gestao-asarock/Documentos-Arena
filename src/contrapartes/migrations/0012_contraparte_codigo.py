"""
Código público da contraparte (AGENTS.md D59).

Escrita à mão, em três passos, porque o campo é **único** e as contrapartes já
existem: criar a coluna já com `unique=True` faria todas as linhas antigas
nascerem com o mesmo valor vazio e a migration falharia no índice. Então cria
solta, preenche, e só aí aplica a restrição.

O preenchimento importa `gerar_codigo` do módulo em vez de copiar a função para
cá. É o oposto do conselho usual sobre migrations, e de propósito: o valor
precisa ser exatamente o mesmo que o `save()` produz hoje e produzirá amanhã.
Uma cópia congelada aqui poderia divergir em silêncio e gerar código diferente
para o mesmo documento, que é o único jeito de este recurso falhar de verdade.
"""

from django.db import migrations, models

from contrapartes.codigo import CARACTERES, gerar_codigo


def preencher(apps, schema_editor):
    Contraparte = apps.get_model("contrapartes", "Contraparte")
    for pk, documento in Contraparte.objects.values_list("pk", "documento").iterator():
        Contraparte.objects.filter(pk=pk).update(codigo=gerar_codigo(documento))


class Migration(migrations.Migration):
    dependencies = [
        ("contrapartes", "0011_help_text_sem_travessao"),
    ]

    operations = [
        migrations.AddField(
            model_name="contraparte",
            name="codigo",
            field=models.CharField(
                blank=True, editable=False, max_length=CARACTERES, verbose_name="código"
            ),
        ),
        # A reversa é `noop`: desfazer esta migration derruba a coluna inteira
        # no `RemoveField` que o Django gera para o `AddField` acima, então não
        # há nada para limpar antes.
        migrations.RunPython(preencher, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="contraparte",
            name="codigo",
            field=models.CharField(
                blank=True,
                editable=False,
                max_length=CARACTERES,
                unique=True,
                verbose_name="código",
            ),
        ),
    ]
