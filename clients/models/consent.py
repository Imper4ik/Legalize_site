from __future__ import annotations

import hashlib
import hmac
from typing import TYPE_CHECKING, Any

from django.conf import settings
from django.db import models, transaction
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

if TYPE_CHECKING:
    from django.http import HttpRequest

    from clients.models import Case, Client

# Field separator that cannot appear in the hashed values (ASCII unit separator),
# so the canonical payload is unambiguous and not forgeable by value collision.
_HASH_SEP = "\x1f"


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
    """Append-only, tamper-evident log of RODO/GDPR consent events.

    Each grant or withdrawal is written as a new immutable row so the
    controller can demonstrate *when* and *to what* the subject consented
    (art. 7(1) RODO) and that withdrawal is as easy as granting (art. 7(3)).
    The current state for a purpose is the most recent row by ``created_at``.

    Integrity is enforced, not merely documented:

    - **Append-only**: :meth:`save` refuses to modify an existing row and
      :meth:`delete` refuses instance deletion, so a consent decision cannot be
      silently rewritten or erased once recorded.
    - **Tamper-evident hash chain**: every row stores ``entry_hash`` — an
      HMAC-SHA256 over its content plus the previous row's hash for the same
      client (``prev_hash``). Altering, deleting, reordering, or back-dating any
      row breaks the chain, which :meth:`verify_chain` detects. The HMAC key is
      ``SECRET_KEY`` (same trust model as the case-number hashes), so a party
      with only database access cannot forge a valid chain.
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
    # Tamper-evidence: per-client hash chain. prev_hash links to the previous
    # row's entry_hash; entry_hash covers this row's content plus prev_hash.
    prev_hash = models.CharField(max_length=64, blank=True, default="", editable=False)
    entry_hash = models.CharField(max_length=64, blank=True, default="", editable=False, db_index=True)

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

    # --- Tamper-evident hash chain -------------------------------------------

    def _canonical_payload(self, prev_hash: str) -> str:
        """Deterministic string of the immutable fields, for hashing."""
        return _HASH_SEP.join(
            [
                str(self.client_id or ""),
                str(self.purpose or ""),
                "1" if self.granted else "0",
                str(self.policy_version or ""),
                str(self.channel or ""),
                str(self.ip_address or ""),
                str(self.user_agent or ""),
                self.created_at.isoformat() if self.created_at else "",
                prev_hash or "",
            ]
        )

    @staticmethod
    def _hash(canonical: str) -> str:
        secret = str(getattr(settings, "SECRET_KEY", ""))
        return hmac.new(secret.encode("utf-8"), canonical.encode("utf-8"), hashlib.sha256).hexdigest()

    def compute_entry_hash(self, prev_hash: str) -> str:
        return self._hash(self._canonical_payload(prev_hash))

    def _latest_prev_hash(self) -> str:
        return (
            type(self)
            .objects.filter(client_id=self.client_id)
            .order_by("-created_at", "-id")
            .values_list("entry_hash", flat=True)
            .first()
            or ""
        )

    def save(self, *args: Any, **kwargs: Any) -> None:
        # Append-only: an already-persisted row can never be rewritten.
        if not self._state.adding:
            raise ValueError(
                "ConsentRecord is append-only; existing rows cannot be modified."
            )
        if self.created_at is None:
            self.created_at = timezone.now()
        if not self.entry_hash:
            self.prev_hash = self._latest_prev_hash()
            self.entry_hash = self.compute_entry_hash(self.prev_hash)
        super().save(*args, **kwargs)

    def delete(self, using: Any = None, keep_parents: bool = False) -> tuple[int, dict[str, int]]:
        raise ValueError("ConsentRecord is append-only; rows cannot be deleted.")

    @classmethod
    def verify_chain(cls, client: Client) -> tuple[bool, ConsentRecord | None]:
        """Recompute the hash chain for a client.

        Returns ``(True, None)`` when intact, or ``(False, row)`` pointing at the
        first row whose stored hash does not match — evidence of tampering,
        deletion, or reordering.
        """
        prev = ""
        for row in cls.objects.filter(client=client).order_by("created_at", "id"):
            expected = row.compute_entry_hash(prev)
            if row.prev_hash != prev or row.entry_hash != expected:
                return False, row
            prev = row.entry_hash
        return True, None

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
        # Atomic so the hash-chain read (previous row) and this insert cannot
        # interleave with a concurrent write for the same client.
        with transaction.atomic():
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
