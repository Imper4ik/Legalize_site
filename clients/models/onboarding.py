from django.conf import settings
from django.db import models
from fernet_fields import EncryptedTextField

class ClientOnboardingSession(models.Model):
    client = models.ForeignKey("clients.Client", on_delete=models.CASCADE, related_name="onboarding_sessions")
    payment = models.ForeignKey("clients.Payment", null=True, blank=True, on_delete=models.SET_NULL)

    token_hash = models.CharField(max_length=64, db_index=True)
    status = models.CharField(
        max_length=32,
        choices=[
            ("created", "Created"),
            ("payment_pending", "Payment pending"),
            ("active", "Active"),
            ("completed", "Completed"),
            ("expired", "Expired"),
            ("revoked", "Revoked"),
        ],
        default="created",
    )

    expires_at = models.DateTimeField()
    completed_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Session for {self.client} - {self.status}"


class ClientDigitalAccess(models.Model):
    client = models.OneToOneField("clients.Client", on_delete=models.CASCADE, related_name="digital_access")

    has_pesel = models.BooleanField(default=False)
    pesel = EncryptedTextField(null=True, blank=True)
    pesel_hash = models.CharField(max_length=64, null=True, blank=True, db_index=True)
    pesel_verified = models.BooleanField(default=False)

    has_trusted_profile = models.BooleanField(default=False)
    trusted_profile_confirmed_at = models.DateTimeField(null=True, blank=True)

    has_mos_account = models.BooleanField(default=False)
    mos_account_confirmed_at = models.DateTimeField(null=True, blank=True)

    needs_pesel_application = models.BooleanField(default=False)
    needs_trusted_profile_instruction = models.BooleanField(default=False)
    needs_mos_instruction = models.BooleanField(default=False)

    notes = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Digital Access for {self.client}"


class MOSApplicationData(models.Model):
    client = models.OneToOneField("clients.Client", on_delete=models.CASCADE, related_name="mos_application_data")

    status = models.CharField(
        max_length=40,
        choices=[
            ("draft", "Draft"),
            ("client_filling", "Client filling"),
            ("client_completed", "Client completed"),
            ("staff_review", "Staff review"),
            ("needs_correction", "Needs correction"),
            ("approved_by_staff", "Approved by staff"),
            ("mos_package_ready", "MOS package ready"),
            ("submitted_in_mos", "Submitted in MOS"),
            ("fingerprints", "Fingerprints"),
            ("waiting_decision", "Waiting decision"),
            ("decision_received", "Decision received"),
            ("closed", "Closed"),
        ],
        default="draft",
    )

    mos_purpose = models.CharField(max_length=64, blank=True)

    legal_stay_until = models.DateField(null=True, blank=True, verbose_name="Legal stay valid until")

    personal_data = models.JSONField(default=dict, blank=True)
    passport_data = models.JSONField(default=dict, blank=True)
    address_data = models.JSONField(default=dict, blank=True)
    stay_data = models.JSONField(default=dict, blank=True)
    previous_stays = models.JSONField(default=list, blank=True)
    travel_history = models.JSONField(default=list, blank=True)
    insurance_data = models.JSONField(default=dict, blank=True)
    financial_data = models.JSONField(default=dict, blank=True)
    legal_declarations = models.JSONField(default=dict, blank=True)

    justification = models.TextField(blank=True)

    client_confirmed_at = models.DateTimeField(null=True, blank=True)
    staff_reviewed_at = models.DateTimeField(null=True, blank=True)
    staff_reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="reviewed_mos_applications",
    )

    staff_notes = models.TextField(blank=True)
    correction_message = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"MOS Data for {self.client} - {self.status}"


class PeselApplication(models.Model):
    client = models.ForeignKey("clients.Client", on_delete=models.CASCADE, related_name="pesel_applications")

    status = models.CharField(
        max_length=40,
        choices=[
            ("not_needed", "Not needed"),
            ("needs_data", "Needs data"),
            ("data_completed", "Data completed"),
            ("staff_review", "Staff review"),
            ("draft_ready", "Draft ready"),
            ("sent_to_client", "Sent to client"),
            ("waiting_for_client_visit", "Waiting for client visit"),
            ("pesel_received", "PESEL received"),
            ("cancelled", "Cancelled"),
        ],
        default="needs_data",
    )

    legal_basis = models.TextField(blank=True)

    pesel_form_data = models.JSONField(default=dict, blank=True)

    generated_pdf = models.FileField(upload_to="pesel_applications/", null=True, blank=True)
    signed_scan = models.FileField(upload_to="pesel_signed/", null=True, blank=True)

    staff_checked_at = models.DateTimeField(null=True, blank=True)
    staff_checked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="checked_pesel_applications",
    )

    notes = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"PESEL App for {self.client} - {self.status}"


from django.db.models.signals import post_save
from django.dispatch import receiver

@receiver(post_save, sender="clients.Client")
def create_client_onboarding_profiles(sender, instance, created, **kwargs):
    if created:
        ClientDigitalAccess.objects.get_or_create(client=instance)
        MOSApplicationData.objects.get_or_create(client=instance)

