"""Client and persistence utilities for monitoring inPOL case statuses.

The watcher works against the documented JSON/XHR endpoints instead of
scraping HTML pages. It authenticates via the ``sign-in`` endpoint, requests
active proceedings from ``active-proceedings`` and persists snapshots in a
local SQLite database so changes between checks can be detected.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Mapping, Optional

import requests
from django.utils import timezone

from clients.models import InpolProceedingSnapshot


@dataclass
class InpolCredentials:
    """Credentials used by the sign-in endpoint."""

    email: str
    password: str


@dataclass
class InpolAuthResult:
    """Authentication response payload and session state."""

    token: Optional[str]
    cookies: requests.cookies.RequestsCookieJar
    payload: Mapping[str, Any]


@dataclass
class InpolProceeding:
    """Single proceeding record returned by ``active-proceedings``."""

    proceeding_id: str
    case_number: str
    status: str
    raw: Mapping[str, Any]

    @classmethod
    def from_api(cls, payload: Mapping[str, Any]) -> "InpolProceeding":
        """Build a proceeding from the API response payload.

        The inPOL API may expose identifiers under different keys depending on
        the account type. This parser aims to be permissive by checking common
        alternatives for the proceeding identifier, case number and status.
        """

        proceeding_id = _coalesce(payload, ["id", "proceedingId", "caseId", "case_id", "caseNumber", "number"])
        case_number = _coalesce(payload, ["caseNumber", "number", "proceedingNumber", "case_id", "id"], default="")
        status = _coalesce(payload, ["status", "state", "decisionStatus", "decision", "phase"], default="")

        if not proceeding_id:
            raise ValueError("Cannot parse proceeding identifier from payload")

        return cls(
            proceeding_id=str(proceeding_id),
            case_number=str(case_number or proceeding_id),
            status=str(status or ""),
            raw=payload,
        )


@dataclass
class InpolChange:
    """Represents a detected change compared to the previous snapshot."""

    proceeding: InpolProceeding
    previous_status: Optional[str]


class InpolClient:
    """HTTP client for the inPOL XHR API."""

    def __init__(self, base_url: str, *, session: Optional[requests.Session] = None, timeout: float = 15.0):
        self.base_url = base_url.rstrip("/")
        self.session = session or requests.Session()
        self.timeout = timeout

    def sign_in(self, credentials: InpolCredentials, endpoint: str = "account/sign-in") -> InpolAuthResult:
        """Authenticate against the sign-in endpoint.

        If the response contains a JWT or access token, it is stored in the
        session as an ``Authorization`` header. Cookies returned by the server
        are also preserved on the session so either auth method can be used for
        subsequent calls.
        """

        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        response = self.session.post(
            url,
            json={"email": credentials.email, "password": credentials.password},
            timeout=self.timeout,
        )
        response.raise_for_status()
        payload: Mapping[str, Any] = response.json()

        token = _coalesce(payload, ["token", "accessToken", "jwt", "access_token"])
        if token:
            self.session.headers.setdefault("Authorization", f"Bearer {token}")

        return InpolAuthResult(token=str(token) if token else None, cookies=self.session.cookies, payload=payload)

    def fetch_active_proceedings(self, endpoint: str = "api/proceedings/active-proceedings") -> List[Mapping[str, Any]]:
        """Return the raw proceedings payload from the active-proceedings endpoint."""

        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        response = self.session.get(url, timeout=self.timeout)
        response.raise_for_status()
        data = response.json()

        if isinstance(data, Mapping):
            # Some deployments wrap the results in a property
            for key in ("proceedings", "data", "results"):
                maybe = data.get(key)
                if isinstance(maybe, list):
                    return maybe
            raise ValueError("Unexpected active-proceedings response format")

        if not isinstance(data, list):
            raise ValueError("active-proceedings must return a list of proceedings")

        return data


class InpolStatusRepository:
    """Database-backed storage for proceedings snapshots using Django models."""

    def load_all(self) -> Dict[str, InpolProceeding]:
        """Return the last stored snapshot as a mapping keyed by proceeding_id."""

        proceedings: Dict[str, InpolProceeding] = {}
        for record in InpolProceedingSnapshot.objects.all():
            proceedings[record.proceeding_id] = InpolProceeding(
                proceeding_id=record.proceeding_id,
                case_number=record.case_number,
                status=record.status,
                raw=record.raw_payload,
            )
        return proceedings

    def save_snapshot(self, proceedings: Iterable[InpolProceeding]) -> None:
        """Persist the current snapshot, upserting by proceeding_id."""

        for proceeding in proceedings:
            InpolProceedingSnapshot.objects.update_or_create(
                proceeding_id=proceeding.proceeding_id,
                defaults={
                    "case_number": proceeding.case_number,
                    "status": proceeding.status,
                    "raw_payload": proceeding.raw,
                    "updated_at": timezone.now(),
                },
            )


class InpolStatusWatcher:
    """Coordinates authentication, retrieval and change detection."""

    def __init__(self, client: InpolClient, repository: InpolStatusRepository):
        self.client = client
        self.repository = repository

    def check(self, credentials: InpolCredentials) -> List[InpolChange]:
        """Authenticate, fetch proceedings, persist them and return any changes."""

        self.client.sign_in(credentials)
        active_payloads = self.client.fetch_active_proceedings()
        current = [InpolProceeding.from_api(item) for item in active_payloads]

        previous = self.repository.load_all()
        changes: List[InpolChange] = []

        for proceeding in current:
            previous_status = previous.get(proceeding.proceeding_id)
            if previous_status is None or previous_status.status != proceeding.status:
                changes.append(
                    InpolChange(
                        proceeding=proceeding,
                        previous_status=previous_status.status if previous_status else None,
                    )
                )

        self.repository.save_snapshot(current)
        return changes


def _coalesce(source: Mapping[str, Any], keys: List[str], default: Any = None) -> Any:
    for key in keys:
        if key in source and source[key] not in (None, ""):
            return source[key]
    return default


__all__ = [
    "InpolAuthResult",
    "InpolChange",
    "InpolClient",
    "InpolCredentials",
    "InpolProceeding",
    "InpolStatusRepository",
    "InpolStatusWatcher",
]
