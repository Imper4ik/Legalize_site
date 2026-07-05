from __future__ import annotations

from typing import TYPE_CHECKING, Any

from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

if TYPE_CHECKING:
    from django.http import HttpRequest

    from clients.models import Case, Client


def _request_ip(request: HttpRequest | None) -> str | None:
    """Best-effort client IP for the consent audit trail.

    Mirrors ``legalize_site.security._client_ip`` but tolerates a missing
    request (e.g. consent recorded from a management command).
    """
    if request is None:
        return None
    forwarded_for = str(request.META.get("HTTP_X_FORWARDED_FOR", ""))
    if forwarded_for:
        return forwarded_for.split(",")[0].strip() or None
    return str(request.META.get("REMOTE_ADDR", "") or "") or None


class ConsentRecord(models.Model):
    """Append-only log of RODO/GDPR consent events for a data subject.

    Each grant or withdrawal is written as a new immutable row so the
    controller can demonstrate *when* and *to what* the subject consented
    (art. 7(1) RODO) and that withdrawal is as easy as granting (art. 7(3)).
    The current state for a purpose is the most recent row by ``created_at``.
    """

    class Purpose(models.TextChoices):
        DATA_PROCESSING = "data_processing", _("Обработка персональных данных")
        SERVICE_PROVISION = "service_provision", _("Оказание услуг по делу")
        MARKETING = "marketing", _("Маркетинговые сообщения")

    class Channel(models.TextChoices):
        ONBOARDING = "onboarding", _("Онбординг")
        SIGNUP = "signup", _("Регистрация")
        STAFF = "staff", _("Сотрудник")
        PORTAL = "portal", _("Личный кабинет")

    client = models.ForeignKey(
        "clients.Client",
        on_delete=models.CASCADE,
        related_name="consents",
    )
    case = models.ForeignKey(
        "clients.Case",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="consents",
    )
    purpose = models.CharField(max_length=32, choices=Purpose.choices)
    granted = models.BooleanField(
        default=True,
        help_text=_("True — согласие дано; False — согласие отозвано."),
    )
    policy_version = models.CharField(max_length=32, blank=True, default="")
    channel = models.CharField(
        max_length=16,
        choices=Channel.choices,
        default=Channel.ONBOARDING,
    )
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=512, blank=True, default="")
    created_at = models.DateTimeField(default=timezone.now, editable=False)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["client", "purpose", "-created_at"]),
        ]
        verbose_name = _("Запись согласия")
        verbose_name_plural = _("Записи согласия")

    def __str__(self) -> str:
        state = "granted" if self.granted else "withdrawn"
        return f"Consent[{self.purpose}={state}] client={self.client_id}"

    @classmethod
    def record(
        cls,
        *,
        client: Client,
        purpose: str,
        granted: bool,
        policy_version: str = "",
        channel: str = Channel.ONBOARDING,
        case: Case | None = None,
        request: HttpRequest | None = None,
    ) -> ConsentRecord:
        """Write a new consent event row."""
        user_agent = ""
        if request is not None:
            user_agent = str(request.META.get("HTTP_USER_AGENT", ""))[:512]
        return cls.objects.create(
            client=client,
            case=case,
            purpose=purpose,
            granted=granted,
            policy_version=policy_version,
            channel=channel,
            ip_address=_request_ip(request),
            user_agent=user_agent,
        )

    @classmethod
    def current_status(cls, client: Client) -> dict[str, ConsentRecord]:
        """Latest consent row per purpose for a client."""
        latest: dict[str, ConsentRecord] = {}
        for record in cls.objects.filter(client=client).order_by("created_at"):
            latest[record.purpose] = record
        return latest

    @classmethod
    def is_granted(cls, client: Client, purpose: str) -> bool:
        """Whether the subject's most recent decision for ``purpose`` is a grant."""
        record = (
            cls.objects.filter(client=client, purpose=purpose)
            .order_by("-created_at")
            .first()
        )
        return bool(record and record.granted)
