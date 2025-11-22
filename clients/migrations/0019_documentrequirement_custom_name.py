from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('clients', '0018_alter_document_document_type_documentrequirement'),
    ]

    operations = [
        migrations.AddField(
            model_name='documentrequirement',
            name='custom_name',
            field=models.CharField(blank=True, max_length=255, verbose_name='Название документа'),
        ),
        migrations.AlterField(
            model_name='documentrequirement',
            name='document_type',
            field=models.CharField(max_length=50, verbose_name='Тип документа'),
        ),
    ]
