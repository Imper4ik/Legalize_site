from __future__ import annotations

from typing import Any, Self

from django.db import models, transaction
from django.utils import timezone


class SoftDeleteQuerySet(models.QuerySet):
    def active(self) -> Self:
        return self.filter(archived_at__isnull=True)

    def archived(self) -> Self:
        return self.filter(archived_at__isnull=False)

    def production(self) -> Self:
        """Exclude non-production (Demo/Test Center) records.

        Used by autonomous background tasks so the unattended reminder loop never
        processes or emails seeded demo/test data. Fields are checked at runtime
        so the method is safe on models that only carry one of the flags.
        """
        qs = self
        field_names = {field.name for field in self.model._meta.get_fields()}
        for flag in ("is_demo_data", "is_test_data"):
            if flag in field_names:
                qs = qs.filter(**{flag: False})
        return qs

    def delete(self) -> tuple[int, dict[str, int]]:
        count = 0
        for obj in self:
            if hasattr(obj, 'archive'):
                obj.archive(save=True)
                count += 1
        return count, {self.model._meta.label: count}

    def hard_delete(self) -> tuple[int, dict[str, int]]:
        return super().delete()

    def restore(self) -> int:
        return super().update(archived_at=None)


class SoftDeleteManager(models.Manager):
    def get_queryset(self) -> SoftDeleteQuerySet:
        return SoftDeleteQuerySet(self.model, using=self._db).active()


class SoftDeleteModel(models.Model):
    archived_at = models.DateTimeField(null=True, blank=True, db_index=True)

    objects = SoftDeleteManager()
    all_objects = SoftDeleteQuerySet.as_manager()

    class Meta:
        abstract = True
        base_manager_name = "objects"
        default_manager_name = "objects"

    @property
    def is_archived(self) -> bool:
        return self.archived_at is not None

    def archive(self, *, save: bool = True) -> Self:
        if self.archived_at is None:
            self.archived_at = timezone.now()
            with transaction.atomic():
                if save:
                    type(self).all_objects.filter(pk=self.pk).update(archived_at=self.archived_at)
                on_archive = getattr(self, "on_archive", None)
                if callable(on_archive):
                    on_archive()
        return self

    def restore(self, *, save: bool = True) -> Self:
        if self.archived_at is not None:
            self.archived_at = None
            with transaction.atomic():
                if save:
                    type(self).all_objects.filter(pk=self.pk).update(archived_at=None)
                on_restore = getattr(self, "on_restore", None)
                if callable(on_restore):
                    on_restore()
        return self

    def delete(self, using: Any = None, keep_parents: bool = False, *, hard: bool = False) -> tuple[int, dict[str, int]]:
        if hard:
            return super().delete(using=using, keep_parents=keep_parents)
        self.archive(save=True)
        return 1, {self._meta.label: 1}
