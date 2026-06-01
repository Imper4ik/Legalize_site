from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any, Iterable, TYPE_CHECKING, cast

from django.conf import settings
from django.core.mail import send_mail
from django.utils import timezone

from clients.models import Client, EmailCampaign, EmailLog
from clients.services.notifications import _log_email, _send_confirmation_email, build_email_idempotency_key

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractBaseUser, AnonymousUser

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CampaignProcessingResult:
    campaign_id: int
    status: str
    sent_count: int
    failed_count: int
    processed: bool


def _send_campaign_mail_with_retry(subject: str, message: str, recipient: str) -> int:
    attempts = max(
        1,
        int(getattr(settings, "EMAIL_CAMPAIGN_RETRY_ATTEMPTS", getattr(settings, "EMAIL_SEND_RETRY_ATTEMPTS", 3))),
    )
    backoff = float(
        getattr(
            settings,
            "EMAIL_CAMPAIGN_RETRY_BACKOFF_SECONDS",
            getattr(settings, "EMAIL_SEND_RETRY_BACKOFF_SECONDS", 0.25),
        )
    )
    for attempt in range(1, attempts + 1):
        try:
            return send_mail(subject, message, settings.DEFAULT_FROM_EMAIL, [recipient])
        except Exception as exc:
            logger.warning(
                "Mass email attempt failed: attempt=%s max_attempts=%s error_type=%s",
                attempt,
                attempts,
                type(exc).__name__,
            )
            if attempt < attempts and backoff > 0:
                time.sleep(backoff * attempt)
    raise RuntimeError(f"campaign send_mail failed after {attempts} attempt(s)")


def normalize_recipient_emails(recipient_emails: Iterable[str]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()

    for raw_email in recipient_emails:
        email = (raw_email or "").strip()
        if not email or email in seen:
            continue
        seen.add(email)
        normalized.append(email)

    return normalized


def queue_mass_email_campaign(
    *,
    subject: str,
    message: str,
    recipient_emails: Iterable[str],
    created_by: AbstractBaseUser | AnonymousUser | None = None,
    filters_snapshot: dict[str, Any] | None = None,
) -> EmailCampaign:
    normalized_recipients = normalize_recipient_emails(recipient_emails)
    if not normalized_recipients:
        raise ValueError("Mass email campaign requires at least one recipient")

    # AnonymousUser cannot be assigned to ForeignKey
    creator = created_by if created_by and created_by.is_authenticated else None

    campaign = EmailCampaign(
        subject=subject,
        message=message,
        total_recipients=len(normalized_recipients),
        filters_snapshot=filters_snapshot or {},
        created_by=cast(Any, creator),
    )
    campaign.set_recipient_emails(normalized_recipients)
    campaign.save()
    return campaign


def _claim_pending_campaign(campaign_id: int) -> EmailCampaign | None:
    started_at = timezone.now()
    updated = EmailCampaign.objects.filter(
        pk=campaign_id,
        status=EmailCampaign.STATUS_PENDING,
    ).update(
        status=EmailCampaign.STATUS_RUNNING,
        started_at=started_at,
        completed_at=None,
        sent_count=0,
        failed_count=0,
        error_details="",
    )
    if not updated:
        return None

    return EmailCampaign.objects.select_related("created_by").get(pk=campaign_id)


def process_campaign(campaign_id: int) -> CampaignProcessingResult | None:
    campaign = _claim_pending_campaign(campaign_id)
    if campaign is None:
        return None

    recipients = normalize_recipient_emails(campaign.recipient_emails_list)
    if not recipients:
        campaign.status = EmailCampaign.STATUS_FAILED
        campaign.error_details = "Campaign has no recipients."
        campaign.completed_at = timezone.now()
        campaign.save(update_fields=["status", "error_details", "completed_at"])
        logger.warning("Email campaign %s failed because it has no recipients", campaign_id)
        return CampaignProcessingResult(
            campaign_id=campaign.id,
            status=campaign.status,
            sent_count=campaign.sent_count,
            failed_count=campaign.failed_count,
            processed=True,
        )

    sent = 0
    failed = 0
    errors: list[str] = []
    clients_by_email = {
        client.email: client
        for client in Client.objects.filter(email__in=recipients).only("id", "email")
    }

    logger.info(
        "Processing email campaign %s with %s recipient(s)",
        campaign.id,
        len(recipients),
    )

    batch_size = max(1, int(getattr(settings, "EMAIL_CAMPAIGN_BATCH_SIZE", 50)))
    batch_delay = max(0.0, float(getattr(settings, "EMAIL_CAMPAIGN_BATCH_DELAY_SECONDS", 0)))

    for index, email_addr in enumerate(recipients, start=1):
        idempotency_key = build_email_idempotency_key("mass_email", campaign.pk, email_addr)
        if idempotency_key and EmailLog.objects.filter(idempotency_key=idempotency_key, delivery_status="sent").exists():
            sent += 1
            continue

        try:
            result = _send_campaign_mail_with_retry(campaign.subject, campaign.message, email_addr)
            if result:
                sent += 1
                _log_email(
                    campaign.subject,
                    campaign.message,
                    [email_addr],
                    client=clients_by_email.get(email_addr),
                    template_type="mass_email",
                    sent_by=campaign.created_by,
                    idempotency_key=idempotency_key,
                )
            else:
                failed += 1
                errors.append(f"recipient #{index}: send_mail returned 0")
                _log_email(
                    campaign.subject,
                    campaign.message,
                    [email_addr],
                    client=clients_by_email.get(email_addr),
                    template_type="mass_email",
                    sent_by=campaign.created_by,
                    idempotency_key=idempotency_key,
                    delivery_status="failed",
                    error_message="send returned 0",
                )
        except Exception as exc:  # pragma: no cover - defensive safeguard
            failed += 1
            errors.append(f"recipient #{index}: {type(exc).__name__}")
            logger.warning(
                "Mass email delivery failed for campaign=%s recipient_index=%s error_type=%s",
                campaign.id,
                index,
                type(exc).__name__,
            )
            _log_email(
                campaign.subject,
                campaign.message,
                [email_addr],
                client=clients_by_email.get(email_addr),
                template_type="mass_email",
                sent_by=campaign.created_by,
                idempotency_key=idempotency_key,
                delivery_status="failed",
                error_message=type(exc).__name__,
            )

        EmailCampaign.objects.filter(pk=campaign.pk).update(
            sent_count=sent,
            failed_count=failed,
        )
        if batch_delay and index % batch_size == 0 and index < len(recipients):
            time.sleep(batch_delay)

    try:
        _send_confirmation_email(
            f"[Mass email] {campaign.subject}",
            campaign.message,
            recipients,
        )
    except Exception as exc:  # pragma: no cover - defensive safeguard
        logger.warning(
            "Failed to send confirmation email for campaign %s: error_type=%s",
            campaign.id,
            type(exc).__name__,
        )

    campaign.sent_count = sent
    campaign.failed_count = failed
    campaign.error_details = "\n".join(errors) if errors else ""
    campaign.status = EmailCampaign.STATUS_COMPLETED if failed == 0 else EmailCampaign.STATUS_FAILED
    campaign.completed_at = timezone.now()
    campaign.save(
        update_fields=[
            "sent_count",
            "failed_count",
            "error_details",
            "status",
            "completed_at",
        ]
    )

    logger.info(
        "Email campaign %s finished with status=%s sent=%s failed=%s",
        campaign.id,
        campaign.status,
        sent,
        failed,
    )
    return CampaignProcessingResult(
        campaign_id=campaign.id,
        status=campaign.status,
        sent_count=sent,
        failed_count=failed,
        processed=True,
    )


def process_pending_email_campaigns(*, limit: int | None = None) -> list[CampaignProcessingResult]:
    pending_ids = list(
        EmailCampaign.objects.filter(status=EmailCampaign.STATUS_PENDING)
        .order_by("created_at")
        .values_list("id", flat=True)[:limit]
    )

    results: list[CampaignProcessingResult] = []
    for campaign_id in pending_ids:
        result = process_campaign(campaign_id)
        if result is not None:
            results.append(result)
    return results
