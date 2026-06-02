import os
import sys
import django
from datetime import date, timedelta
from decimal import Decimal

# Setup Django environment
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from legalize_site.env import load_env
load_env()

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "legalize_site.settings.development")
django.setup()

if os.environ.get("ALLOW_PRODUCTION_DATA_MUTATION") != "yes":
    raise SystemExit(
        "Refusing to mutate data. Set ALLOW_PRODUCTION_DATA_MUTATION=yes only for a reviewed test-data seeding run."
    )

from django.db import connection
from django.core.files.base import ContentFile
from clients.models import Client, Document, Payment, Reminder
from clients.constants import DocumentType

# Configure output encoding for Windows terminal
sys.stdout.reconfigure(encoding='utf-8')

print("--- Starting Production Test Clients Seeding ---")

# Print target database to be safe (no passwords!)
db_host = connection.settings_dict.get('HOST')
db_port = connection.settings_dict.get('PORT')
db_name = connection.settings_dict.get('NAME')
print(f"Target DB: {db_host}:{db_port}/{db_name}")

try:
    # 1. Clean up any existing production test clients
    test_emails = [
        "prod-test-work@example.com",
        "prod-test-study@example.com",
        "prod-test-spouse@example.com",
        "prod-test-child@example.com"
    ]
    deleted_count, _ = Client.all_objects.filter(email__in=test_emails).hard_delete()
    print(f"Cleaned up {deleted_count} old test clients.")

    # 2. Create Work Client
    # Represents application purpose 'work' with fingerprints stage and ZUS RCA uploaded
    client_work = Client.objects.create(
        first_name="ProdWork",
        last_name="Test",
        email="prod-test-work@example.com",
        phone="+48500100200",
        citizenship="BY",
        language="ru",
        application_purpose="work",
        basis_of_stay="Karta Pobytu",
        case_number="WSC-II-12345/2026",
        legal_basis_end_date=date.today() + timedelta(days=90),
        workflow_stage="fingerprints",
    )
    print(f"Created Work Client: {client_work.get_full_name()} ({client_work.email})")

    # Set legal stay until 10 days from now (should generate warning reminders)
    mos_data = client_work.mos_application_data
    mos_data.legal_stay_until = date.today() + timedelta(days=10)
    mos_data.save()

    # Upload ZALACZNIK_NR_1 to store Company NIP
    doc_nip = Document.objects.create(
        client=client_work,
        document_type=DocumentType.ZALACZNIK_NR_1.value,
        ocr_status="success",
        parsed_data={"nip": "5252344078"}
    )
    doc_nip.file.save("contract.pdf", ContentFile(b"%PDF-1.4\n% Mock PDF"))
    print("Uploaded ZALACZNIK_NR_1 document with NIP 5252344078.")

    # Upload ZUS RCA with valid NIP and period month, verifying that bypassing
    # insurance code checks keeps ocr_name_mismatch = False
    doc_zus = Document.objects.create(
        client=client_work,
        document_type=DocumentType.ZUS_RCA_OR_INSURANCE.value,
        zus_period_month=date(2026, 5, 1),
        ocr_status="success",
        ocr_name_mismatch=False,  # This should remain False because we bypass number/insurance code check!
        parsed_data={
            "employer_nip": "5252344078",
            "detected_names": ["ProdWork Test"],
            "period_month": "2026-05-01",
            "warnings": [],
            "infos": ["Insurance code 011000 detected. (Bypassed number check)"]
        }
    )
    doc_zus.file.save("zus_rca.pdf", ContentFile(b"%PDF-1.4\n% Mock PDF"))
    print("Uploaded ZUS RCA document (month=05.2026, company NIP=5252344078).")

    # 3. Create Study Client
    # Represents application purpose 'study' with an overdue partial payment
    client_study = Client.objects.create(
        first_name="ProdStudy",
        last_name="Test",
        email="prod-test-study@example.com",
        phone="+48500100300",
        citizenship="UA",
        language="en",
        application_purpose="study",
        basis_of_stay="Visa D",
        case_number="WSC-II-54321/2026",
        legal_basis_end_date=date.today() + timedelta(days=60),
        workflow_stage="document_collection",
    )
    print(f"Created Study Client: {client_study.get_full_name()} ({client_study.email})")

    # Add overdue payment
    Payment.objects.create(
        client=client_study,
        service_description="study_course_fee",
        total_amount=Decimal("2000.00"),
        amount_paid=Decimal("500.00"),
        status="partial",
        due_date=date.today() - timedelta(days=5),
    )
    print("Created overdue payment of 1500.00 PLN.")

    # 4. Create Family Spouse Client
    # Represents application purpose 'family' with spouse role
    client_spouse = Client.objects.create(
        first_name="ProdSpouse",
        last_name="Test",
        email="prod-test-spouse@example.com",
        phone="+48500100400",
        citizenship="US",
        language="ru",
        application_purpose="family",
        family_role="family_spouse",
        sponsor_client=client_work,
        basis_of_stay="Visa D",
        case_number="WSC-II-67890/2026",
        legal_basis_end_date=date.today() + timedelta(days=120),
        workflow_stage="new_client",
    )
    print(f"Created Family Spouse Client: {client_spouse.get_full_name()} ({client_spouse.email})")

    # 5. Create Family Child Client
    # Represents application purpose 'family' with child role
    client_child = Client.objects.create(
        first_name="ProdChild",
        last_name="Test",
        email="prod-test-child@example.com",
        phone="+48500100500",
        citizenship="UA",
        language="pl",
        application_purpose="family",
        family_role="family_child",
        sponsor_client=client_work,
        basis_of_stay="Visa D",
        case_number="WSC-II-11111/2026",
        legal_basis_end_date=date.today() + timedelta(days=120),
        workflow_stage="new_client",
    )
    print(f"Created Family Child Client: {client_child.get_full_name()} ({client_child.email})")

    print("\nVerification Checklist:")
    for client in [client_work, client_study, client_spouse, client_child]:
        checklist = client.get_document_checklist()
        print(f" - {client.get_full_name()} (purpose: {client.get_document_requirement_purpose()}): {len(checklist)} items required.")

    print("\n--- Seeding Completed Successfully ---")

except Exception as e:
    print(f"\nError occurred: {e}", file=sys.stderr)
    raise e
