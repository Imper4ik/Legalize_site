from __future__ import annotations

from django.db import models


class DatabaseMediaFile(models.Model):
    name = models.CharField(max_length=512, unique=True, db_index=True)
    content = models.BinaryField()
    content_type = models.CharField(max_length=255, blank=True, default="")
    size = models.BigIntegerField(default=0)
    sha256 = models.CharField(max_length=64, blank=True, db_index=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "database media file"
        verbose_name_plural = "database media files"

    def __str__(self) -> str:
        return self.name
