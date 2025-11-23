"""Client and persistence utilities for monitoring inPOL case statuses.

The watcher works against the documented JSON/XHR endpoints instead of
scraping HTML pages. It authenticates via the ``sign-in`` endpoint, requests
active proceedings from ``active-proceedings`` and persists snapshots in the
project database (e.g., Railway PostgreSQL) so changes between checks can be
detected.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Mapping, Optional

import requests
from django.utils import timezone

from clients.models import Client, InpolProceedingSnapshot


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
        self.base_url = _normalize_base_url(base_url)
        self.session = session or requests.Session()
        self.timeout = timeout

        # Use browser-like defaults to avoid WAF blocking scripted requests
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
            "Referer": self.base_url,
        })

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


class InpolCaseUpdater:
    """Propagates detected inPOL changes into related ``Client`` records."""

    def __init__(self, client_model=Client):
        self.client_model = client_model

    def apply_changes(self, changes: Iterable[InpolChange], *, account_email: Optional[str] = None) -> None:
        """Update matching clients with case numbers and latest inPOL status."""

        for change in changes:
            self._apply_change(change, account_email)

    def apply_changes_for_client(
        self,
        changes: Iterable[InpolChange],
        target_client: Client,
        *,
        account_email: Optional[str] = None,
    ) -> List[InpolChange]:
        """Apply updates only to the specified client and return applied changes."""

        applied: List[InpolChange] = []

        for change in changes:
            proceeding = change.proceeding
            case_number = proceeding.case_number.strip() if proceeding.case_number else ""

            matches_case = bool(case_number and target_client.case_number and target_client.case_number == case_number)
            matches_email = bool(
                account_email and target_client.email and target_client.email.lower() == account_email.lower()
            )

            if not (matches_case or matches_email):
                continue

            updates: Dict[str, Any] = {
                "inpol_status": proceeding.status,
                "inpol_updated_at": timezone.now(),
            }

            if case_number and not target_client.case_number:
                updates["case_number"] = case_number

            self.client_model.objects.filter(pk=target_client.pk).update(**updates)
            applied.append(change)

        return applied

    def _apply_change(self, change: InpolChange, account_email: Optional[str]) -> None:
        proceeding = change.proceeding
        case_number = proceeding.case_number.strip() if proceeding.case_number else ""

        matched_clients: List[Client] = []

        if case_number:
            matched_clients = list(self.client_model.objects.filter(case_number=case_number))

        if not matched_clients and account_email:
            matched_clients = list(self.client_model.objects.filter(email__iexact=account_email))

        if not matched_clients:
            return

        for client in matched_clients:
            updates: Dict[str, Any] = {
                "inpol_status": proceeding.status,
                "inpol_updated_at": timezone.now(),
            }

            if case_number and not client.case_number:
                updates["case_number"] = case_number

            self.client_model.objects.filter(pk=client.pk).update(**updates)


def check_inpol_and_update_clients(
    credentials: InpolCredentials,
    client: InpolClient,
    repository: InpolStatusRepository,
    *,
    case_updater: Optional[InpolCaseUpdater] = None,
) -> List[InpolChange]:
    """Run the watcher and push detected changes into ``Client`` records."""

    watcher = InpolStatusWatcher(client, repository)
    changes = watcher.check(credentials)

    updater = case_updater or InpolCaseUpdater()
    updater.apply_changes(changes, account_email=credentials.email)

    return changes


def check_inpol_for_client(
    credentials: InpolCredentials,
    client: InpolClient,
    repository: InpolStatusRepository,
    *,
    target_client: Client,
    case_updater: Optional[InpolCaseUpdater] = None,
) -> List[InpolChange]:
    """Run the watcher and apply only changes relevant to a specific client."""

    watcher = InpolStatusWatcher(client, repository)
    changes = watcher.check(credentials)

    updater = case_updater or InpolCaseUpdater()
    return updater.apply_changes_for_client(changes, target_client, account_email=credentials.email)


def _coalesce(source: Mapping[str, Any], keys: List[str], default: Any = None) -> Any:
    for key in keys:
        if key in source and source[key] not in (None, ""):
            return source[key]
    return default


def _normalize_base_url(base_url: str) -> str:
    """Remove trailing ``/login`` so API calls hit the correct inPOL host."""

    parsed = requests.utils.urlparse(base_url.strip())
    path = parsed.path.rstrip("/")

    if path.endswith("/login"):
        path = path[: -len("/login")].rstrip("/")

    normalized = parsed._replace(path=path, params="", query="", fragment="")
    return requests.utils.urlunparse(normalized).rstrip("/")


__all__ = [
    "InpolAuthResult",
    "InpolChange",
    "InpolClient",
    "InpolCredentials",
    "InpolProceeding",
    "InpolCaseUpdater",
    "InpolStatusRepository",
    "InpolStatusWatcher",
    "check_inpol_and_update_clients",
    "check_inpol_for_client",
]
