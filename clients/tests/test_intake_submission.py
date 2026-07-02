from __future__ import annotations

import pytest
from django.core.exceptions import ValidationError
from django.test import Client as DjangoClient
from django.urls import reverse
from django.utils import timezone

from clients.models import (
    CaseParticipant,
    Client,
    ClientIntakeSubmission,
    ClientOnboardingSession,
    MOSApplicationData,
)
from clients.services.intake import convert_intake_submission
from clients.services.onboarding_tokens import generate_onboarding_token, hash_onboarding_token
from clients.tests.factories import create_staff_user


def _submission(**overrides):
    defaults = {
        "token_hash": "a" * 64,
        "status": ClientIntakeSubmission.STATUS_SUBMITTED,
        "personal_data": {
            "first_name": "Ivan",
            "last_name": "Ivanov",
            "email": "IVAN@example.com",
            "phone": "+48 500 100 200",
            "birth_date": "1990-05-15",
            "citizenship": "UA",
            "document_number": " AB 123456 ",
            "language": "ru",
        },
        "case_data": {
            "application_purpose": "work",
            "application_type": "temporary_residence",
            "basis_of_stay": "employment",
            "workflow_stage": "document_collection",
            "status": "pending",
            "submission_date": "2026-06-01",
        },
    }
    defaults.update(overrides)
    return ClientIntakeSubmission.objects.create(**defaults)


@pytest.mark.django_db
def test_intake_submission_hashes_lookup_fields_without_plaintext_indexes():
    submission = _submission()

    assert submission.email_hash
    assert submission.phone_hash
    assert submission.passport_hash
    assert len(submission.email_hash) == 64
    assert submission.email_hash != submission.personal_data["email"]
    assert submission.passport_hash != submission.personal_data["document_number"]


@pytest.mark.django_db
def test_convert_intake_creates_client_primary_case_and_mos_data():
    submission = _submission()

    result = convert_intake_submission(submission)

    client = result.client
    assert client.first_name == "Ivan"
    assert client.last_name == "Ivanov"
    assert client.email == "ivan@example.com"
    assert client.phone == "+48 500 100 200"
    assert client.birth_date.isoformat() == "1990-05-15"
    assert client.citizenship == "UA"
    assert str(client.passport_num) == " AB 123456 "
    assert client.language == "ru"

    case = result.case
    assert case.client == client
    assert client.cases.count() == 1
    assert case.application_purpose == "work"
    assert case.application_type == "temporary_residence"
    assert case.basis_of_stay == "employment"
    assert case.workflow_stage == "document_collection"
    assert case.status == "pending"
    assert case.submission_date.isoformat() == "2026-06-01"
    assert CaseParticipant.objects.filter(case=case, client=client, role="principal").exists()

    mos_data = MOSApplicationData.objects.get(client=client, case=case)
    assert mos_data.status == "client_completed"
    assert mos_data.personal_data["email"] == "IVAN@example.com"
    assert mos_data.passport_data["document_number"] == " AB 123456 "

    submission.refresh_from_db()
    assert submission.status == ClientIntakeSubmission.STATUS_CONVERTED
    assert submission.created_client == client
    assert submission.created_case == case


@pytest.mark.django_db
def test_convert_intake_requires_staff_review_for_contact_conflicts():
    Client.objects.create(first_name="Existing", last_name="Client", email="ivan@example.com")
    submission = _submission(token_hash="b" * 64)

    with pytest.raises(ValidationError):
        convert_intake_submission(submission)

    submission.refresh_from_db()
    assert submission.status == ClientIntakeSubmission.STATUS_NEEDS_REVIEW
    assert submission.created_client_id is None
    assert Client.objects.filter(email="ivan@example.com").count() == 1


@pytest.mark.django_db
def test_staff_can_convert_reviewed_conflicting_intake_without_merging_clients():
    existing = Client.objects.create(first_name="Existing", last_name="Client", email="ivan@example.com")
    submission = _submission(token_hash="c" * 64, status=ClientIntakeSubmission.STATUS_NEEDS_REVIEW)

    result = convert_intake_submission(submission, allow_conflicts=True)

    assert result.client.pk != existing.pk
    assert result.client.email == "ivan@example.com"
    assert result.case.client == result.client
    assert Client.objects.filter(email="ivan@example.com").count() == 2


@pytest.mark.django_db
def test_intake_save_rejects_created_client_case_mismatch():
    client_a = Client.objects.create(first_name="A", last_name="Client")
    client_b = Client.objects.create(first_name="B", last_name="Client")
    other_case = client_b.cases.get()

    with pytest.raises(ValidationError):
        ClientIntakeSubmission.objects.create(
            token_hash="d" * 64,
            personal_data={"first_name": "A", "last_name": "Client"},
            created_client=client_a,
            created_case=other_case,
        )


@pytest.mark.django_db
def test_convert_intake_marks_expired_submission():
    submission = _submission(token_hash="e" * 64, expires_at=timezone.now() - timezone.timedelta(minutes=1))

    with pytest.raises(ValidationError):
        convert_intake_submission(submission)

    submission.refresh_from_db()
    assert submission.status == ClientIntakeSubmission.STATUS_EXPIRED
    assert submission.created_client_id is None


def _valid_public_post(**overrides):
    data = {
        "first_name": "Public",
        "last_name": "Applicant",
        "email": "public-applicant@example.com",
        "phone": "+48500100200",
        "birth_date": "1991-04-20",
        "citizenship": "UA",
        "passport_number": "PX123456",
        "language": "en",
        "application_purpose": "work",
        "application_type": "temporary_residence",
        "basis_of_stay": "employment",
        "password": "SafePass123!",
        "password_confirm": "SafePass123!",
    }
    data.update(overrides)
    return data


@pytest.mark.django_db
def test_staff_can_generate_public_intake_link():
    staff = create_staff_user()
    http = DjangoClient()
    http.force_login(staff)

    response = http.post(reverse("clients:create_public_intake_link"), {"application_purpose": "work"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert "/intake/" in payload["link"]

    raw_token = payload["link"].rstrip("/").split("/")[-1]
    intake = ClientIntakeSubmission.objects.get(token_hash=hash_onboarding_token(raw_token))
    assert intake.status == ClientIntakeSubmission.STATUS_DRAFT
    assert intake.case_data["application_purpose"] == "work"
    assert intake.created_by == staff


@pytest.mark.django_db
def test_public_intake_get_renders_form_for_anonymous_user():
    raw_token, token_hash = generate_onboarding_token()
    ClientIntakeSubmission.objects.create(
        token_hash=token_hash,
        status=ClientIntakeSubmission.STATUS_DRAFT,
        case_data={"application_purpose": "study"},
        expires_at=timezone.now() + timezone.timedelta(hours=1),
    )

    response = DjangoClient().get(reverse("clients:public_intake", kwargs={"token": raw_token}))

    assert response.status_code == 200
    assert b'name="first_name"' in response.content
    assert b'name="application_purpose"' in response.content


@pytest.mark.django_db
def test_public_intake_post_creates_client_case_and_onboarding_session():
    raw_token, token_hash = generate_onboarding_token()
    intake = ClientIntakeSubmission.objects.create(
        token_hash=token_hash,
        status=ClientIntakeSubmission.STATUS_DRAFT,
        expires_at=timezone.now() + timezone.timedelta(hours=1),
    )

    response = DjangoClient().post(
        reverse("clients:public_intake", kwargs={"token": raw_token}),
        _valid_public_post(),
    )

    assert response.status_code == 302
    assert "/onboarding/" in response["Location"]

    intake.refresh_from_db()
    assert intake.status == ClientIntakeSubmission.STATUS_CONVERTED
    assert intake.created_client is not None
    assert intake.created_case is not None

    client = intake.created_client
    case = intake.created_case
    assert client.email == "public-applicant@example.com"
    assert client.birth_date.isoformat() == "1991-04-20"
    assert str(client.passport_num) == "PX123456"
    assert case.client == client
    assert case.application_purpose == "work"
    assert case.application_type == "temporary_residence"
    assert case.basis_of_stay == "employment"
    assert client.user is not None
    assert client.user.has_usable_password()
    session = ClientOnboardingSession.objects.get(client=client, case=case, scope="case_link")
    assert session.status == "active"


@pytest.mark.django_db
def test_public_intake_conflict_goes_to_review_without_merging():
    Client.objects.create(first_name="Existing", last_name="Client", email="public-applicant@example.com")
    raw_token, token_hash = generate_onboarding_token()
    intake = ClientIntakeSubmission.objects.create(
        token_hash=token_hash,
        status=ClientIntakeSubmission.STATUS_DRAFT,
        expires_at=timezone.now() + timezone.timedelta(hours=1),
    )

    response = DjangoClient().post(
        reverse("clients:public_intake", kwargs={"token": raw_token}),
        _valid_public_post(),
    )

    assert response.status_code == 200
    intake.refresh_from_db()
    assert intake.status == ClientIntakeSubmission.STATUS_NEEDS_REVIEW
    assert intake.created_client_id is None
    assert Client.objects.filter(email="public-applicant@example.com").count() == 1


@pytest.mark.django_db
def test_public_intake_hijack_prevention():
    from django.contrib.auth import get_user_model
    User = get_user_model()

    # Create staff user
    staff_user = User.objects.create_user(
        email="staff-member@example.com",
        password="old-secure-password",
        is_staff=True,
    )
    # Create regular user
    regular_user = User.objects.create_user(
        email="client-user@example.com",
        password="client-secure-password",
    )

    raw_token, token_hash = generate_onboarding_token()
    intake = ClientIntakeSubmission.objects.create(
        token_hash=token_hash,
        status=ClientIntakeSubmission.STATUS_DRAFT,
        expires_at=timezone.now() + timezone.timedelta(hours=1),
    )

    # 1. Attempt to hijack staff user
    payload = _valid_public_post()
    payload["email"] = "staff-member@example.com"
    payload["password"] = "new-insecure-password"
    payload["password_confirm"] = "new-insecure-password"

    from django.utils import translation
    with translation.override("ru"):
        response = DjangoClient().post(
            reverse("clients:public_intake", kwargs={"token": raw_token}),
            payload,
        )

    assert response.status_code == 200
    form = response.context["form"]
    assert "email" in form.errors
    assert "Этот email зарегистрирован для служебного аккаунта. Пожалуйста, используйте другой email." in form.errors["email"]

    # Verify password was NOT changed
    staff_user.refresh_from_db()
    assert staff_user.check_password("old-secure-password")
    assert not staff_user.check_password("new-insecure-password")

    # 2. Attempt to hijack regular user
    payload["email"] = "client-user@example.com"
    with translation.override("ru"):
        response = DjangoClient().post(
            reverse("clients:public_intake", kwargs={"token": raw_token}),
            payload,
        )

    assert response.status_code == 200
    form = response.context["form"]
    assert "email" in form.errors
    assert "Пользователь с таким email уже зарегистрирован. Пожалуйста, войдите в систему или восстановите пароль." in form.errors["email"]

    # Verify password was NOT changed
    regular_user.refresh_from_db()
    assert regular_user.check_password("client-secure-password")
    assert not regular_user.check_password("new-insecure-password")
