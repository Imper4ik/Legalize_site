from django.db import models


class OptimisticLockingMixin(models.Model):
    class Meta:
        abstract = True
