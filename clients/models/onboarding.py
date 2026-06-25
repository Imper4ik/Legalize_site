from typing import Any

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils.translation import gettext_lazy as _

from fernet_fields import EncryptedJSONField, EncryptedTextField


class ClientOnboardingSession(models.Model):
    client = models.ForeignKey("clients.Client", on_delete=models.CASCADE, related_name="onboarding_sessions")
    case = models.ForeignKey(
        "clients.Case",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="onboarding_sessions",
    )
    payment = models.ForeignKey("clients.Payment", null=True, blank=True, on_delete=models.SET_NULL)
    scope = models.CharField(
        max_length=20,
        choices=[
            ("case_link", "Ссылка на дело"),
            ("client_portal", "Портал клиента"),
        ],
        default="case_link",
    )

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

    is_demo_data = models.BooleanField(default=False, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(scope="case_link", case__isnull=False)
                    | models.Q(scope="client_portal", case__isnull=True)
                ),
                name="onboarding_scope_matches_case",
            )
        ]

    def clean(self) -> None:
        super().clean()
        # client_portal sessions must never carry a Case (the DB check
        # constraint enforces case IS NULL); the case is chosen per-request and
        # kept in the server-side session instead.
        if self.scope == "client_portal":
            if self.case_id is not None:
                raise ValidationError({"case": "Портальная сессия не может быть привязана к делу."})
        elif self.case_id is None:
            if self.payment_id and self.payment.case_id:
                self.case_id = self.payment.case_id
            elif self.client_id:
                from clients.services.cases import get_legacy_compatibility_case
                try:
                    self.case = get_legacy_compatibility_case(self.client_id, self.__class__.__name__)
                except ValidationError as e:
                    raise ValidationError({"case": e.message})
            else:
                raise ValidationError({"case": "Case is required."})
        if self.case_id and self.client_id and self.case.client_id != self.client_id:
            raise ValidationError("Клиент и дело не согласованы.")

    def save(self, *args: object, **kwargs: object) -> None:
        update_fields = kwargs.get("update_fields")
        # Only case_link sessions auto-resolve a Case; client_portal stays NULL.
        if self.scope != "client_portal" and self.case_id is None:
            if self.payment_id and self.payment.case_id:
                self.case_id = self.payment.case_id
            elif self.client_id:
                from clients.services.cases import get_legacy_compatibility_case
                self.case = get_legacy_compatibility_case(self.client_id, self.__class__.__name__)
            if self.case_id is not None and update_fields is not None:
                update_fields = set(update_fields)
                update_fields.add("case")
                kwargs["update_fields"] = list(update_fields)
        super().save(*args, **kwargs)

    def __str__(self) -> str:
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

    def __str__(self) -> str:
        return f"Digital Access for {self.client}"


class MOSApplicationData(models.Model):
    NEW_CARD_STATUS_YES = "yes"
    NEW_CARD_STATUS_NO = "no"
    NEW_CARD_STATUS_UNKNOWN = "unknown"
    NEW_CARD_STATUS_CHOICES = [
        ("", _("Not provided")),
        (NEW_CARD_STATUS_YES, _("Tak / Да")),
        (NEW_CARD_STATUS_NO, _("Nie / Нет")),
        (NEW_CARD_STATUS_UNKNOWN, _("Nie wiem / Не знаю")),
    ]

    client = models.ForeignKey("clients.Client", on_delete=models.CASCADE, related_name="mos_applications")
    case = models.OneToOneField(
        "clients.Case",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="mos_application_data",
    )

    status = models.CharField(
        max_length=40,
        choices=[
            ("draft", _("Draft")),
            ("client_filling", _("Client filling")),
            ("client_completed", _("Client completed")),
            ("staff_review", _("Staff review")),
            ("needs_correction", _("Needs correction")),
            ("approved_by_staff", _("Approved by staff")),
            ("mos_package_ready", _("MOS package ready")),
            ("submitted_in_mos", _("Submitted in MOS")),
            ("fingerprints", _("Fingerprints")),
            ("waiting_decision", _("Waiting decision")),
            ("decision_received", _("Decision received")),
            ("closed", _("Closed")),
        ],
        default="draft",
    )

    mos_purpose = models.CharField(max_length=64, blank=True)

    legal_stay_until = models.DateField(null=True, blank=True, verbose_name="Legal stay valid until")

    personal_data = EncryptedJSONField(default=dict, blank=True)
    passport_data = EncryptedJSONField(default=dict, blank=True)
    address_data = EncryptedJSONField(default=dict, blank=True)
    stay_data = EncryptedJSONField(default=dict, blank=True)
    previous_stays = EncryptedJSONField(default=list, blank=True)
    travel_history = EncryptedJSONField(default=list, blank=True)
    insurance_data = EncryptedJSONField(default=dict, blank=True)
    financial_data = EncryptedJSONField(default=dict, blank=True)
    legal_declarations = EncryptedJSONField(default=dict, blank=True)

    new_residence_card_application_status = models.CharField(
        max_length=16,
        choices=NEW_CARD_STATUS_CHOICES,
        blank=True,
        default="",
    )
    new_residence_card_case_number = EncryptedTextField(blank=True, default="")
    new_residence_card_submitted_at = models.DateField(null=True, blank=True)
    new_residence_card_comment = models.TextField(blank=True)
    new_residence_card_updated_at = models.DateTimeField(null=True, blank=True)

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
    version = models.PositiveIntegerField(default=1)

    def clean(self) -> None:
        super().clean()
        if self.case_id is None:
            if self.client_id:
                from clients.services.cases import get_legacy_compatibility_case
                try:
                    self.case = get_legacy_compatibility_case(self.client_id, self.__class__.__name__)
                except ValidationError as e:
                    raise ValidationError({"case": e.message})
            else:
                raise ValidationError({"case": "Case is required."})
        if self.case_id and self.client_id and self.case.client_id != self.client_id:
            raise ValidationError("Клиент и дело не согласованы.")

    def save(self, *args: object, **kwargs: object) -> None:
        update_fields = kwargs.get("update_fields")
        if self.case_id is None and self.client_id:
            from clients.services.cases import get_legacy_compatibility_case
            self.case = get_legacy_compatibility_case(self.client_id, self.__class__.__name__)
            if update_fields is not None:
                update_fields = set(update_fields)
                update_fields.add("case")
                kwargs["update_fields"] = list(update_fields)
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"MOS Data for {self.client} - {self.status}"


class PeselApplication(models.Model):
    client = models.ForeignKey("clients.Client", on_delete=models.CASCADE, related_name="pesel_applications")
    case = models.ForeignKey(
        "clients.Case",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="pesel_applications",
    )

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

    pesel_form_data = EncryptedJSONField(default=dict, blank=True)

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
    version = models.PositiveIntegerField(default=1)

    def clean(self) -> None:
        super().clean()
        if self.case_id is None:
            if self.client_id:
                from clients.services.cases import get_legacy_compatibility_case
                try:
                    self.case = get_legacy_compatibility_case(self.client_id, self.__class__.__name__)
                except ValidationError as e:
                    raise ValidationError({"case": e.message})
            else:
                raise ValidationError({"case": "Case is required."})
        if self.case_id and self.client_id and self.case.client_id != self.client_id:
            raise ValidationError("Клиент и дело не согласованы.")

    def save(self, *args: object, **kwargs: object) -> None:
        update_fields = kwargs.get("update_fields")
        if self.case_id is None and self.client_id:
            from clients.services.cases import get_legacy_compatibility_case
            self.case = get_legacy_compatibility_case(self.client_id, self.__class__.__name__)
            if update_fields is not None:
                update_fields = set(update_fields)
                update_fields.add("case")
                kwargs["update_fields"] = list(update_fields)
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"PESEL App for {self.client} - {self.status}"


@receiver(post_save, sender="clients.Client")
def create_client_onboarding_profiles(sender: object, instance: Any, created: bool, **kwargs: object) -> None:
    if created:
        ClientDigitalAccess.objects.get_or_create(client=instance)
        case = instance.cases.order_by("opened_at", "id").first()
        if case:
            MOSApplicationData.objects.get_or_create(client=instance, case=case)
