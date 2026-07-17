from __future__ import annotations

from datetime import date
from unittest.mock import Mock, patch

import pytest
from cryptography.fernet import Fernet
from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection
from django.urls import reverse
from django.utils.translation import gettext

from clients.constants import DocumentType
from clients.models import Client, ClientIntakeSubmission, Document, MOSApplicationData
from clients.security.encrypted import (
    EncryptedJSONUnavailableError,
    EncryptedTextUnavailableError,
)
from clients.services.document_workflow import (
    confirm_wezwanie_document,
    enqueue_document_processing_job,
    process_pending_document_jobs,
)
from clients.services.intake import convert_intake_submission, find_existing_client_conflicts
from clients.services.intake_extraction import pre_fill_mos_data_from_ocr
from clients.services.mos_eligibility import evaluate_mos_eligibility
from clients.services.onboarding_tokens import hash_onboarding_token
from clients.services.rental_parser import RentalDocData
from clients.services.wezwanie_parser import WezwanieData
from clients.tests.factories import create_manager_user

CORRUPTED_FERNET_TOKEN = "gAAAA-corrupted-json-token"


def _corrupt_json_field(
    instance: object,
    field_name: str,
    raw_value: str = CORRUPTED_FERNET_TOKEN,
) -> None:
    meta = instance._meta  # type: ignore[attr-defined]
    table = connection.ops.quote_name(meta.db_table)
    column = connection.ops.quote_name(meta.get_field(field_name).column)
    pk_column = connection.ops.quote_name(meta.pk.column)
    with connection.cursor() as cursor:
        cursor.execute(
            f"UPDATE {table} SET {column} = %s WHERE {pk_column} = %s",
            [raw_value, instance.pk],  # type: ignore[attr-defined]
        )


def _raw_json_field(instance: object, field_name: str) -> str:
    meta = instance._meta  # type: ignore[attr-defined]
    table = connection.ops.quote_name(meta.db_table)
    column = connection.ops.quote_name(meta.get_field(field_name).column)
    pk_column = connection.ops.quote_name(meta.pk.column)
    with connection.cursor() as cursor:
        cursor.execute(
            f"SELECT {column} FROM {table} WHERE {pk_column} = %s",
            [instance.pk],  # type: ignore[attr-defined]
        )
        row = cursor.fetchone()
    assert row is not None
    return str(row[0])


def _pdf_upload(name: str) -> SimpleUploadedFile:
    return SimpleUploadedFile(
        name,
        b"%PDF-1.4\n1 0 obj<</Type/Catalog>>endobj\ntrailer<</Root 1 0 R>>\n%%EOF",
        content_type="application/pdf",
    )


@pytest.mark.django_db
def test_mos_review_reads_safely_and_approve_fails_closed(client) -> None:
    manager = create_manager_user(email="encrypted-json-review@example.com")
    crm_client = Client.objects.create(
        first_name="Original",
        last_name="Client",
        email="encrypted-json-client@example.com",
        application_purpose="family",
        family_role="family_spouse",
    )
    case = crm_client.cases.get()
    mos_data = MOSApplicationData.objects.get(case=case)
    mos_data.status = "client_completed"
    mos_data.personal_data = {"first_name": "Replacement"}
    mos_data.stay_data = {"is_in_poland": False}
    mos_data.save(update_fields=["status", "personal_data", "stay_data"])
    _corrupt_json_field(mos_data, "personal_data")
    mos_data = MOSApplicationData.objects.get(pk=mos_data.pk)

    # Advisory checks stay available when their own encrypted JSON is readable.
    assert evaluate_mos_eligibility(crm_client, mos_data).eligible is False

    client.force_login(manager)
    url = reverse("clients:admin_mos_review", kwargs={"client_id": crm_client.pk})
    assert client.get(url).status_code == 200
    assert client.post(url, {"action": "approve"}).status_code == 302

    crm_client.refresh_from_db()
    mos_data.refresh_from_db()
    assert crm_client.first_name == "Original"
    assert mos_data.status == "client_completed"
    assert mos_data.staff_reviewed_at is None
    assert _raw_json_field(mos_data, "personal_data") == CORRUPTED_FERNET_TOKEN


@pytest.mark.django_db
def test_mos_eligibility_treats_unavailable_stay_data_as_unknown() -> None:
    crm_client = Client.objects.create(
        first_name="Family",
        last_name="Member",
        application_purpose="family",
        family_role="family_child",
    )
    mos_data = MOSApplicationData.objects.get(case=crm_client.cases.get())
    mos_data.stay_data = {"is_in_poland": False}
    mos_data.save(update_fields=["stay_data"])
    _corrupt_json_field(mos_data, "stay_data")
    mos_data = MOSApplicationData.objects.get(pk=mos_data.pk)

    result = evaluate_mos_eligibility(crm_client, mos_data)

    assert result.eligible is True
    assert result.has_warnings is False
    assert _raw_json_field(mos_data, "stay_data") == CORRUPTED_FERNET_TOKEN


@pytest.mark.django_db
def test_intake_conversion_rejects_unavailable_source_without_writes() -> None:
    submission = ClientIntakeSubmission.objects.create(
        token_hash="f" * 64,
        status=ClientIntakeSubmission.STATUS_SUBMITTED,
        personal_data={
            "first_name": "Encrypted",
            "last_name": "Intake",
            "email": "encrypted-intake@example.com",
        },
        case_data={"application_purpose": "work"},
    )
    _corrupt_json_field(submission, "personal_data")
    submission = ClientIntakeSubmission.objects.get(pk=submission.pk)
    client_count = Client.objects.count()

    assert find_existing_client_conflicts(submission).count() == 0
    with pytest.raises(EncryptedJSONUnavailableError):
        convert_intake_submission(submission)

    submission.refresh_from_db()
    assert submission.status == ClientIntakeSubmission.STATUS_SUBMITTED
    assert submission.created_client_id is None
    assert Client.objects.count() == client_count
    assert _raw_json_field(submission, "personal_data") == CORRUPTED_FERNET_TOKEN


@pytest.mark.django_db
def test_passport_prefill_rejects_unavailable_destination_without_overwrite() -> None:
    crm_client = Client.objects.create(first_name="Passport", last_name="Client")
    case = crm_client.cases.get()
    mos_data = MOSApplicationData.objects.get(case=case)
    mos_data.personal_data = {"existing": "value"}
    mos_data.passport_data = {"existing_document": "value"}
    mos_data.save(update_fields=["personal_data", "passport_data"])
    passport_raw_before = _raw_json_field(mos_data, "passport_data")
    Document.objects.create(
        client=crm_client,
        case=case,
        document_type=DocumentType.PASSPORT.value,
        file=_pdf_upload("prefill-passport.pdf"),
        ocr_status="success",
        parsed_data={"first_name": "Changed", "passport_number": "AB123"},
    )
    _corrupt_json_field(mos_data, "personal_data")
    mos_data = MOSApplicationData.objects.get(pk=mos_data.pk)

    with pytest.raises(EncryptedJSONUnavailableError):
        pre_fill_mos_data_from_ocr(mos_data)

    assert _raw_json_field(mos_data, "personal_data") == CORRUPTED_FERNET_TOKEN
    assert _raw_json_field(mos_data, "passport_data") == passport_raw_before


@pytest.mark.django_db
@patch("clients.services.rental_parser.parse_rental_doc")
def test_rental_ocr_retries_unavailable_address_and_continues_batch(parse_mock) -> None:
    parse_mock.return_value = RentalDocData(
        text="Rental agreement for Jan Kowalski at Main 1, 00-001 Warsaw",
        address="Main 1, 00-001 Warsaw",
        valid_until=date(2030, 1, 1),
        detected_names=["Jan Kowalski"],
    )

    blocked_client = Client.objects.create(first_name="Jan", last_name="Kowalski")
    healthy_client = Client.objects.create(first_name="Jan", last_name="Kowalski")
    blocked_case = blocked_client.cases.get()
    healthy_case = healthy_client.cases.get()
    blocked_mos = MOSApplicationData.objects.get(case=blocked_case)
    healthy_mos = MOSApplicationData.objects.get(case=healthy_case)
    for mos_data in (blocked_mos, healthy_mos):
        mos_data.address_data = {
            "street": "Main 1",
            "city": "Warsaw",
            "postal_code": "00-001",
        }
        mos_data.save(update_fields=["address_data"])
    _corrupt_json_field(blocked_mos, "address_data")

    blocked_document = Document.objects.create(
        client=blocked_client,
        case=blocked_case,
        document_type=DocumentType.ADDRESS_PROOF.value,
        file=_pdf_upload("blocked-rental.pdf"),
        parsed_data={"previous": "keep"},
    )
    healthy_document = Document.objects.create(
        client=healthy_client,
        case=healthy_case,
        document_type=DocumentType.ADDRESS_PROOF.value,
        file=_pdf_upload("healthy-rental.pdf"),
    )
    blocked_job = enqueue_document_processing_job(
        document=blocked_document,
        job_type="rental_ocr",
    )
    healthy_job = enqueue_document_processing_job(
        document=healthy_document,
        job_type="rental_ocr",
    )

    results = process_pending_document_jobs(limit=2)

    assert [result.status for result in results] == ["pending", "completed"]
    blocked_job.refresh_from_db()
    healthy_job.refresh_from_db()
    blocked_document.refresh_from_db()
    healthy_document.refresh_from_db()
    assert blocked_job.attempts == 1
    assert blocked_job.status == "pending"
    assert blocked_job.next_attempt_at is not None
    assert blocked_job.error_message == gettext(
        "Onboarding address data is temporarily unavailable."
    )
    assert blocked_document.ocr_status == "failed"
    assert blocked_document.parsed_data == {"previous": "keep"}
    assert healthy_job.status == "completed"
    assert healthy_document.ocr_status == "success"
    assert _raw_json_field(blocked_mos, "address_data") == CORRUPTED_FERNET_TOKEN


@pytest.mark.django_db
def test_intake_status_save_preserves_hashes_when_personal_data_is_unavailable() -> None:
    submission = ClientIntakeSubmission.objects.create(
        token_hash="a" * 64,
        personal_data={
            "email": "hash@example.com",
            "phone": "+48123123123",
            "document_number": "AB12345",
        },
        case_data={"application_purpose": "work"},
    )
    original_hashes = (
        submission.email_hash,
        submission.phone_hash,
        submission.passport_hash,
    )
    _corrupt_json_field(submission, "personal_data")
    submission = ClientIntakeSubmission.objects.get(pk=submission.pk)

    submission.status = ClientIntakeSubmission.STATUS_REVOKED
    submission.save(update_fields=["status", "updated_at"])

    submission.refresh_from_db()
    assert (
        submission.email_hash,
        submission.phone_hash,
        submission.passport_hash,
    ) == original_hashes
    assert _raw_json_field(submission, "personal_data") == CORRUPTED_FERNET_TOKEN


@pytest.mark.django_db
def test_intake_status_save_preserves_hashes_for_malformed_encrypted_json() -> None:
    submission = ClientIntakeSubmission.objects.create(
        token_hash="b" * 64,
        personal_data={
            "email": "malformed@example.com",
            "phone": "+48111222333",
            "document_number": "CD98765",
        },
        case_data={"application_purpose": "work"},
    )
    original_hashes = (
        submission.email_hash,
        submission.phone_hash,
        submission.passport_hash,
    )
    malformed_token = Fernet(settings.FERNET_KEYS[0]).encrypt(b"not-json").decode()
    _corrupt_json_field(submission, "personal_data", malformed_token)
    submission = ClientIntakeSubmission.objects.get(pk=submission.pk)
    assert submission.personal_data == "not-json"

    submission.status = ClientIntakeSubmission.STATUS_REVOKED
    submission.save(update_fields=["status", "updated_at"])

    submission.refresh_from_db()
    assert (
        submission.email_hash,
        submission.phone_hash,
        submission.passport_hash,
    ) == original_hashes
    assert _raw_json_field(submission, "personal_data") == malformed_token


@pytest.mark.django_db
def test_public_intake_get_and_post_fail_closed_on_unavailable_source(client) -> None:
    raw_token = "unavailable-public-intake-token"
    submission = ClientIntakeSubmission.objects.create(
        token_hash=hash_onboarding_token(raw_token),
        status=ClientIntakeSubmission.STATUS_DRAFT,
        personal_data={"first_name": "Existing"},
        case_data={"application_purpose": "work"},
    )
    _corrupt_json_field(submission, "personal_data")
    url = reverse("clients:public_intake", kwargs={"token": raw_token})

    get_response = client.get(url)
    post_response = client.post(url, {"first_name": "Overwrite"})

    assert get_response.status_code == 409
    assert post_response.status_code == 409
    assert CORRUPTED_FERNET_TOKEN not in get_response.content.decode()
    assert CORRUPTED_FERNET_TOKEN not in post_response.content.decode()
    submission.refresh_from_db()
    assert submission.status == ClientIntakeSubmission.STATUS_DRAFT
    assert _raw_json_field(submission, "personal_data") == CORRUPTED_FERNET_TOKEN


@pytest.mark.django_db
def test_document_job_refuses_to_overwrite_unavailable_existing_parsed_data() -> None:
    crm_client = Client.objects.create(first_name="OCR", last_name="Blocked")
    case = crm_client.cases.get()
    document = Document.objects.create(
        client=crm_client,
        case=case,
        document_type=DocumentType.WEZWANIE.value,
        file=_pdf_upload("blocked-wezwanie.pdf"),
        parsed_data={"existing": "preserve"},
    )
    job = enqueue_document_processing_job(document=document)
    _corrupt_json_field(document, "parsed_data")
    parser = Mock()

    results = process_pending_document_jobs(limit=1, parser=parser)

    assert len(results) == 1
    assert results[0].status == "pending"
    parser.assert_not_called()
    job.refresh_from_db()
    assert job.attempts == 1
    assert job.error_message == gettext("Existing OCR data is temporarily unavailable.")
    assert _raw_json_field(document, "parsed_data") == CORRUPTED_FERNET_TOKEN


@pytest.mark.django_db
def test_mos_approval_preserves_unavailable_client_passport_ciphertext(client) -> None:
    manager = create_manager_user(email="encrypted-passport-review@example.com")
    crm_client = Client.objects.create(
        first_name="Passport",
        last_name="Owner",
        passport_num="OLD-PASSPORT",
    )
    case = crm_client.cases.get()
    mos_data = MOSApplicationData.objects.get(case=case)
    mos_data.status = "client_completed"
    mos_data.passport_data = {"document_number": "NEW-PASSPORT"}
    mos_data.save(update_fields=["status", "passport_data"])
    _corrupt_json_field(crm_client, "passport_num")

    client.force_login(manager)
    response = client.post(
        reverse("clients:admin_mos_review", kwargs={"client_id": crm_client.pk}),
        {"action": "approve"},
    )

    assert response.status_code == 302
    mos_data.refresh_from_db()
    assert mos_data.status == "client_completed"
    assert mos_data.staff_reviewed_at is None
    assert _raw_json_field(crm_client, "passport_num") == CORRUPTED_FERNET_TOKEN


@pytest.mark.django_db
@pytest.mark.parametrize(
    "field_name",
    ["address_data", "previous_stays", "travel_history", "legal_declarations"],
)
def test_mos_approval_preflights_all_encrypted_payloads(client, field_name: str) -> None:
    manager = create_manager_user(email=f"encrypted-{field_name}@example.com")
    crm_client = Client.objects.create(first_name="MOS", last_name="Review")
    mos_data = MOSApplicationData.objects.get(case=crm_client.cases.get())
    mos_data.status = "client_completed"
    mos_data.save(update_fields=["status"])
    _corrupt_json_field(mos_data, field_name)

    client.force_login(manager)
    response = client.post(
        reverse("clients:admin_mos_review", kwargs={"client_id": crm_client.pk}),
        {"action": "approve"},
    )

    assert response.status_code == 302
    mos_data.refresh_from_db()
    assert mos_data.status == "client_completed"
    assert mos_data.staff_reviewed_at is None
    assert _raw_json_field(mos_data, field_name) == CORRUPTED_FERNET_TOKEN


@pytest.mark.django_db
def test_wezwanie_confirmation_preserves_unavailable_case_number() -> None:
    crm_client = Client.objects.create(first_name="Case", last_name="Owner")
    case = crm_client.cases.get()
    case.authority_case_number = "OLD-CASE-NUMBER"
    case.save(update_fields=["authority_case_number"])
    document = Document.objects.create(
        client=crm_client,
        case=case,
        document_type=DocumentType.WEZWANIE.value,
        file=_pdf_upload("confirm-wezwanie.pdf"),
        awaiting_confirmation=True,
        parsed_data={"existing": "preserve"},
    )
    parsed_before = _raw_json_field(document, "parsed_data")
    _corrupt_json_field(case, "authority_case_number")
    case.refresh_from_db()
    document.refresh_from_db()

    with pytest.raises(EncryptedTextUnavailableError):
        confirm_wezwanie_document(
            document=document,
            actor=None,
            confirmation_data={"case_number": "NEW-CASE-NUMBER"},
        )

    document.refresh_from_db()
    assert document.awaiting_confirmation is True
    assert _raw_json_field(document, "parsed_data") == parsed_before
    assert _raw_json_field(case, "authority_case_number") == CORRUPTED_FERNET_TOKEN


@pytest.mark.django_db
def test_wezwanie_ocr_retries_when_case_number_ciphertext_is_unavailable() -> None:
    crm_client = Client.objects.create(first_name="OCR", last_name="Case")
    case = crm_client.cases.get()
    case.authority_case_number = "OLD-CASE-NUMBER"
    case.save(update_fields=["authority_case_number"])
    document = Document.objects.create(
        client=crm_client,
        case=case,
        document_type=DocumentType.WEZWANIE.value,
        file=_pdf_upload("queued-wezwanie.pdf"),
        parsed_data={"existing": "preserve"},
    )
    parsed_before = _raw_json_field(document, "parsed_data")
    job = enqueue_document_processing_job(document=document)
    _corrupt_json_field(case, "authority_case_number")
    parser = Mock(return_value=WezwanieData(text="parsed", case_number="NEW-CASE-NUMBER"))

    results = process_pending_document_jobs(limit=1, parser=parser)

    assert len(results) == 1
    assert results[0].status == "pending"
    job.refresh_from_db()
    assert job.status == "pending"
    assert job.error_message == gettext("Existing case data is temporarily unavailable.")
    assert _raw_json_field(document, "parsed_data") == parsed_before
    assert _raw_json_field(case, "authority_case_number") == CORRUPTED_FERNET_TOKEN
