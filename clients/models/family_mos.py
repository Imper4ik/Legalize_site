from django.db import models

class ClientFamilyMemberMOS(models.Model):
    client = models.ForeignKey("clients.Client", on_delete=models.CASCADE, related_name="mos_family_members")

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

    def __str__(self):
        return f"{self.full_name} ({self.relationship}) - {self.client}"
