from django.db import models
from django.core.exceptions import ValidationError

class OptimisticLockingMixin(models.Model):
    class Meta:
        abstract = True

    def clean(self) -> None:
        if self.pk:
            db_version = self.__class__._base_manager.filter(pk=self.pk).values_list('version', flat=True).first()
            if db_version is not None and db_version != self.version:
                raise ValidationError("Данные были изменены другим сотрудником. Проверьте актуальную версию перед сохранением.")
        super().clean()

    def save(self, *args, **kwargs):
        if self.pk:
            db_version = self.__class__._base_manager.filter(pk=self.pk).values_list('version', flat=True).first()
            if db_version is not None and db_version != self.version:
                raise ValidationError("Данные были изменены другим сотрудником. Проверьте актуальную версию перед сохранением.")
            
            self.version += 1
            
            update_fields = kwargs.get("update_fields")
            if update_fields is not None:
                update_fields = set(update_fields)
                update_fields.add("version")
                kwargs["update_fields"] = list(update_fields)
        
        super().save(*args, **kwargs)
