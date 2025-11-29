from __future__ import annotations

from django.db import models
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _


class Submission(models.Model):
    slug = models.SlugField(max_length=64, unique=True, verbose_name=_('Слаг основания'))
    class Status(models.TextChoices):
        DRAFT = 'draft', _('Черновик')
        IN_PROGRESS = 'in_progress', _('В работе')
        COMPLETED = 'completed', _('Завершено')

    name = models.CharField(max_length=255, verbose_name=_('Название основания'))
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.DRAFT,
        verbose_name=_('Статус'),
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_('Дата создания'))

    class Meta:
        verbose_name = _('Основание подачи')
        verbose_name_plural = _('Основания подачи')
        ordering = ['-created_at']

    def __str__(self) -> str:  # pragma: no cover - human friendly
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            base_slug = slugify(self.name, allow_unicode=True) or 'submission'
            candidate = base_slug
            counter = 1

            while Submission.objects.filter(slug=candidate).exclude(pk=self.pk).exists():
                counter += 1
                candidate = f"{base_slug}-{counter}"

            self.slug = candidate

        super().save(*args, **kwargs)


class Document(models.Model):
    class Status(models.TextChoices):
        NOT_UPLOADED = 'not_uploaded', _('Не загружен')
        UPLOADED = 'uploaded', _('Загружен')
        VERIFIED = 'verified', _('Подтверждён')
        REJECTED = 'rejected', _('Отклонён')

    submission = models.ForeignKey(
        Submission,
        on_delete=models.CASCADE,
        related_name='documents',
        verbose_name=_('Основание подачи'),
    )
    title = models.CharField(max_length=255, verbose_name=_('Название документа'))
    file_path = models.FileField(
        upload_to='submission_documents/',
        blank=True,
        null=True,
        verbose_name=_('Файл'),
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.NOT_UPLOADED,
        verbose_name=_('Статус'),
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_('Дата создания'))

    class Meta:
        verbose_name = _('Документ основания')
        verbose_name_plural = _('Документы оснований')
        ordering = ['-created_at']

    def __str__(self) -> str:  # pragma: no cover - human friendly
        return f"{self.title} ({self.get_status_display()})"
