import hashlib
import hmac
from typing import Any

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils.translation import gettext_lazy as _

from clients.models.consistency import assert_case_client_consistent
from fernet_fields import EncryptedJSONField, EncryptedTextField


def _normalize_intake_lookup_value(value: Any, *, field_name: str) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        return ""
    if field_name == "email":
        return normalized.casefold()
    if field_name == "phone":
        return "".join(char for char in normalized if char.isdigit() or char == "+")
    if field_name == "passport":
        return normalized.upper().replace(" ", "")
    return normalized


def _hash_intake_lookup_value(value: Any, *, field_name: str) -> str:
    normalized = _normalize_intake_lookup_value(value, field_name=field_name)
    if not normalized:
        return ""
    secret = str(getattr(settings, "SECRET_KEY", ""))
    return hmac.new(secret.encode("utf-8"), normalized.encode("utf-8"), hashlib.sha256).hexdigest()


class ClientIntakeSubmission(models.Model):
    """Encrypted pre-client questionnaire submitted from a public intake link."""

    STATUS_DRAFT = "draft"
    STATUS_SUBMITTED = "submitted"
    STATUS_NEEDS_REVIEW = "needs_review"
    STATUS_CONVERTED = "converted"
    STATUS_EXPIRED = "expired"
    STATUS_REVOKED = "revoked"
    STATUS_CHOICES = [
        (STATUS_DRAFT, "Draft"),
        (STATUS_SUBMITTED, "Submitted"),
        (STATUS_NEEDS_REVIEW, "Needs staff review"),
        (STATUS_CONVERTED, "Converted to client/case"),
        (STATUS_EXPIRED, "Expired"),
        (STATUS_REVOKED, "Revoked"),
    ]

    SOURCE_PUBLIC_LINK = "public_link"
    SOURCE_STAFF_LINK = "staff_link"
    SOURCE_IMPORT = "import"
    SOURCE_CHOICES = [
        (SOURCE_PUBLIC_LINK, "Public link"),
        (SOURCE_STAFF_LINK, "Staff link"),
        (SOURCE_IMPORT, "Import"),
    ]

    token_hash = models.CharField(max_length=64, unique=True, db_index=True)
    status = models.CharField(max_length=32, choices=STATUS_CHOICES, default=STATUS_DRAFT, db_index=True)
    source = models.CharField(max_length=32, choices=SOURCE_CHOICES, default=SOURCE_PUBLIC_LINK)

    personal_data = EncryptedJSONField(default=dict, blank=True)
    case_data = EncryptedJSONField(default=dict, blank=True)
    staff_notes = models.TextField(blank=True)

    email_hash = models.CharField(max_length=64, blank=True, default="", db_index=True)
    phone_hash = models.CharField(max_length=64, blank=True, default="", db_index=True)
    passport_hash = models.CharField(max_length=64, blank=True, default="", db_index=True)

    created_client = models.ForeignKey(
        "clients.Client",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="intake_submissions",
    )
    created_case = models.ForeignKey(
        "clients.Case",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="intake_submissions",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="created_intake_submissions",
    )
    converted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="converted_intake_submissions",
    )

    expires_at = models.DateTimeField(null=True, blank=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    converted_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["status", "created_at"], name="intake_status_created_idx"),
            models.Index(fields=["email_hash", "status"], name="intake_email_status_idx"),
            models.Index(fields=["phone_hash", "status"], name="intake_phone_status_idx"),
            models.Index(fields=["passport_hash", "status"], name="intake_passport_status_idx"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=(
                    ~models.Q(status="converted")
                    | (models.Q(created_client__isnull=False) & models.Q(created_case__isnull=False))
                ),
                name="intake_converted_has_client_case",
            )
        ]

    def clean(self) -> None:
        super().clean()
        if self.created_client_id and self.created_case_id and self.created_case:
            if self.created_case.client_id != self.created_client_id:
                raise ValidationError("Client and case do not match.")
        if self.status == self.STATUS_CONVERTED and (not self.created_client_id or not self.created_case_id):
            raise ValidationError("Converted intake must reference the created client and case.")

    def _assert_created_case_client_consistent(self) -> None:
        if not self.created_client_id or not self.created_case_id:
            return
        fields_cache = getattr(getattr(self, "_state", None), "fields_cache", {})
        if "created_case" in fields_cache and self.created_case is not None:
            case_client_id = self.created_case.client_id
        else:
            from clients.models.case import Case

            case_client_id = Case.all_objects.only("client_id").get(pk=self.created_case_id).client_id
        if case_client_id != self.created_client_id:
            raise ValidationError("Client and case do not match.")

    def save(self, *args: Any, **kwargs: Any) -> None:
        personal_data = self.personal_data if isinstance(self.personal_data, dict) else {}
        self.email_hash = _hash_intake_lookup_value(personal_data.get("email"), field_name="email")
        self.phone_hash = _hash_intake_lookup_value(personal_data.get("phone"), field_name="phone")
        passport_value = (
            personal_data.get("passport_num")
            or personal_data.get("passport_number")
            or personal_data.get("document_number")
        )
        self.passport_hash = _hash_intake_lookup_value(passport_value, field_name="passport")
        update_fields = kwargs.get("update_fields")
        if update_fields is not None:
            update_fields = set(update_fields)
            update_fields.update({"email_hash", "phone_hash", "passport_hash"})
            kwargs["update_fields"] = list(update_fields)
        self._assert_created_case_client_consistent()
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        personal_data = self.personal_data if isinstance(self.personal_data, dict) else {}
        first_name = str(personal_data.get("first_name") or "").strip()
        last_name = str(personal_data.get("last_name") or "").strip()
        full_name = " ".join(part for part in (first_name, last_name) if part)
        return full_name or f"Intake #{self.pk or 'new'}"


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
                raise ValidationError("Портальная сессия не может быть привязана к делу.")
        elif self.case_id is None:
            payment = self.payment
            if payment is not None and payment.case_id:
                self.case_id = payment.case_id
            elif self.client_id:
                from clients.services.cases import get_legacy_compatibility_case
                try:
                    self.case = get_legacy_compatibility_case(self.client_id, self.__class__.__name__)
                except ValidationError as e:
                    raise ValidationError(e.message)
            else:
                raise ValidationError("Case is required.")
        if self.case_id and self.client_id and self.case and self.case.client_id != self.client_id:
            raise ValidationError("Клиент и дело не согласованы.")

    def save(self, *args: Any, **kwargs: Any) -> None:
        update_fields = kwargs.get("update_fields")
        # Only case_link sessions auto-resolve a Case; client_portal stays NULL.
        if self.scope != "client_portal" and self.case_id is None:
            payment = self.payment
            if payment is not None and payment.case_id:
                self.case_id = payment.case_id
            elif self.client_id:
                from clients.services.cases import get_legacy_compatibility_case
                self.case = get_legacy_compatibility_case(self.client_id, self.__class__.__name__)
            if self.case_id is not None and update_fields is not None:
                update_fields = set(update_fields)
                update_fields.add("case")
                kwargs["update_fields"] = list(update_fields)
        assert_case_client_consistent(self)
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
                    raise ValidationError(e.message)
            else:
                raise ValidationError("Case is required.")
        if self.case_id and self.client_id and self.case and self.case.client_id != self.client_id:
            raise ValidationError("Клиент и дело не согласованы.")

    def save(self, *args: Any, **kwargs: Any) -> None:
        update_fields = kwargs.get("update_fields")
        if self.case_id is None and self.client_id:
            from clients.services.cases import get_legacy_compatibility_case
            self.case = get_legacy_compatibility_case(self.client_id, self.__class__.__name__)
            if update_fields is not None:
                update_fields = set(update_fields)
                update_fields.add("case")
                kwargs["update_fields"] = list(update_fields)
        assert_case_client_consistent(self)
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
                    raise ValidationError(e.message)
            else:
                raise ValidationError("Case is required.")
        if self.case_id and self.client_id and self.case and self.case.client_id != self.client_id:
            raise ValidationError("Клиент и дело не согласованы.")

    def save(self, *args: Any, **kwargs: Any) -> None:
        update_fields = kwargs.get("update_fields")
        if self.case_id is None and self.client_id:
            from clients.services.cases import get_legacy_compatibility_case
            self.case = get_legacy_compatibility_case(self.client_id, self.__class__.__name__)
            if update_fields is not None:
                update_fields = set(update_fields)
                update_fields.add("case")
                kwargs["update_fields"] = list(update_fields)
        assert_case_client_consistent(self)
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
