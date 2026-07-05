from __future__ import annotations

from typing import TYPE_CHECKING

from clients.models import AppSettings, ConsentRecord

if TYPE_CHECKING:
    from django.http import HttpRequest

    from clients.models import Case, Client

# Purposes the data subject must accept to use the service. Marketing is
# intentionally excluded — it is opt-in and captured separately.
REQUIRED_ONBOARDING_PURPOSES = (
    ConsentRecord.Purpose.DATA_PROCESSING,
    ConsentRecord.Purpose.SERVICE_PROVISION,
)


def current_policy_version() -> str:
    return AppSettings.get_solo().privacy_policy_version or ""


def record_onboarding_consent(
    *,
    client: Client,
    case: Case | None = None,
    request: HttpRequest | None = None,
    channel: str = ConsentRecord.Channel.ONBOARDING,
) -> list[ConsentRecord]:
    """Persist the required consents for a subject completing onboarding.

    Idempotent per purpose: skips writing a new row when the subject's most
    recent decision is already a grant, so re-submitting the final step does
    not spam the append-only log.
    """
    policy_version = current_policy_version()
    created: list[ConsentRecord] = []
    for purpose in REQUIRED_ONBOARDING_PURPOSES:
        if ConsentRecord.is_granted(client, purpose):
            continue
        created.append(
            ConsentRecord.record(
                client=client,
                purpose=purpose,
                granted=True,
                policy_version=policy_version,
                channel=channel,
                case=case,
                request=request,
            )
        )
    return created
