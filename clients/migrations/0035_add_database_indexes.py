# Generated manually for database indexes optimization

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('clients', '0034_client_fingerprints_location_and_more'),
    ]

    operations = [
        # ========================================
        # Client model indexes
        # ========================================
        migrations.AlterModelOptions(
            name='client',
            options={
                'ordering': ['-created_at'],
                'verbose_name': 'Клиент',
                'verbose_name_plural': 'Клиенты'
            },
        ),
        migrations.AddIndex(
            model_name='client',
            index=models.Index(fields=['email'], name='client_email_idx'),
        ),
        migrations.AddIndex(
            model_name='client',
            index=models.Index(fields=['case_number_hash'], name='client_case_idx'),
        ),
        migrations.AddIndex(
            model_name='client',
            index=models.Index(fields=['application_purpose'], name='client_purpose_idx'),
        ),
        migrations.AddIndex(
            model_name='client',
            index=models.Index(fields=['status'], name='client_status_idx'),
        ),
        migrations.AddIndex(
            model_name='client',
            index=models.Index(fields=['citizenship'], name='client_citizenship_idx'),
        ),
        migrations.AddIndex(
            model_name='client',
            index=models.Index(fields=['status', '-created_at'], name='client_status_created_idx'),
        ),
        migrations.AddIndex(
            model_name='client',
            index=models.Index(fields=['application_purpose', 'status'], name='client_purpose_status_idx'),
        ),
        migrations.AddIndex(
            model_name='client',
            index=models.Index(fields=['-created_at'], name='client_created_idx'),
        ),
        migrations.AddIndex(
            model_name='client',
            index=models.Index(fields=['last_name', 'first_name'], name='client_name_idx'),
        ),

        # ========================================
        # Payment model indexes
        # ========================================
        migrations.AlterModelOptions(
            name='payment',
            options={
                'ordering': ['-created_at'],
                'verbose_name': 'Платёж',
                'verbose_name_plural': 'Платежи'
            },
        ),
        migrations.AddIndex(
            model_name='payment',
            index=models.Index(fields=['client', 'status'], name='payment_client_status_idx'),
        ),
        migrations.AddIndex(
            model_name='payment',
            index=models.Index(fields=['status'], name='payment_status_idx'),
        ),
        migrations.AddIndex(
            model_name='payment',
            index=models.Index(fields=['service_description'], name='payment_service_idx'),
        ),
        migrations.AddIndex(
            model_name='payment',
            index=models.Index(fields=['due_date'], name='payment_due_date_idx'),
        ),
        migrations.AddIndex(
            model_name='payment',
            index=models.Index(fields=['payment_date'], name='payment_date_idx'),
        ),
        migrations.AddIndex(
            model_name='payment',
            index=models.Index(fields=['client', '-created_at'], name='payment_client_created_idx'),
        ),
        migrations.AddIndex(
            model_name='payment',
            index=models.Index(fields=['status', 'due_date'], name='payment_status_due_idx'),
        ),

        # ========================================
        # Document model indexes
        # ========================================
        migrations.AddIndex(
            model_name='document',
            index=models.Index(fields=['client', 'document_type'], name='doc_client_type_idx'),
        ),
        migrations.AddIndex(
            model_name='document',
            index=models.Index(fields=['client', '-uploaded_at'], name='doc_client_uploaded_idx'),
        ),
        migrations.AddIndex(
            model_name='document',
            index=models.Index(fields=['document_type'], name='doc_type_idx'),
        ),
        migrations.AddIndex(
            model_name='document',
            index=models.Index(fields=['verified'], name='doc_verified_idx'),
        ),
        migrations.AddIndex(
            model_name='document',
            index=models.Index(fields=['awaiting_confirmation'], name='doc_await_confirm_idx'),
        ),
        migrations.AddIndex(
            model_name='document',
            index=models.Index(fields=['expiry_date'], name='doc_expiry_idx'),
        ),
        migrations.AddIndex(
            model_name='document',
            index=models.Index(fields=['client', 'expiry_date'], name='doc_client_expiry_idx'),
        ),
    ]
