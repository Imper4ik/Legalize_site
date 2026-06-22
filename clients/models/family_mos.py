from django.db import models


class ClientFamilyMemberMOS(models.Model):
    client = models.ForeignKey("clients.Client", on_delete=models.CASCADE, related_name="mos_family_members")
    case = models.ForeignKey(
        "clients.Case",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="mos_family_members",
    )

    full_name = models.CharField(max_length=255)
    gender = models.CharField(max_length=1, choices=[("M", "M"), ("K", "K")])
    birth_date = models.DateField(null=True, blank=True)
    relationship = models.CharField(max_length=100, blank=True)
    citizenship = models.CharField(max_length=100, blank=True)
    residence_place = models.CharField(max_length=255, blank=True)

    applies_for_temporary_residence = models.BooleanField(default=False)
    is_dependent_on_client = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def save(self, *args: object, **kwargs: object) -> None:
        update_fields = kwargs.get("update_fields")
        if self.case_id is None and self.client_id:
            from clients.services.cases import get_primary_case_for_client_id

            self.case = get_primary_case_for_client_id(self.client_id)
            if update_fields is not None:
                update_fields = set(update_fields)
                update_fields.add("case")
                kwargs["update_fields"] = list(update_fields)
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.full_name} ({self.relationship}) - {self.client}"
