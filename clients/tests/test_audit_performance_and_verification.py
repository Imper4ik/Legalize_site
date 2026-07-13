from datetime import date

from django.db import connection
from django.test.utils import CaptureQueriesContext

from clients.constants import DocumentType
from clients.models import Client, Document, DocumentRequirement, WniosekAttachment, WniosekSubmission
from clients.services.wniosek import build_submitted_document_summary
from clients.services.zus import uploaded_zus_months


def test_unverified_zus_document_not_uploaded(db):
    client = Client.objects.create(first_name="ZUS", last_name="Test", application_purpose="work")

    # 1. Create ZUS document but keep it unverified=False
    doc = Document.objects.create(
        client=client,
        document_type=DocumentType.ZUS_RCA_OR_INSURANCE.value,
        zus_period_month=date(2026, 5, 1),
        verified=False,
    )

    # It should not count as uploaded because it is unverified
    assert date(2026, 5, 1) not in uploaded_zus_months(client)

    # 2. Verify the document
    doc.verified = True
    doc.save()

    # Now it should be counted
    assert date(2026, 5, 1) in uploaded_zus_months(client)

    # 3. Archive the document
    doc.archived_at = date(2026, 6, 1)
    doc.save()

    # Archived documents should not count
    assert date(2026, 5, 1) not in uploaded_zus_months(client)


def test_build_submitted_document_summary_zero_queries_with_prefetch(db):
    client = Client.objects.create(first_name="Wniosek", last_name="Test", application_purpose="work")
    submission = WniosekSubmission.objects.create(
        client=client,
        document_kind="wezwanie",
        attachment_count=1,
    )
    WniosekAttachment.objects.create(
        submission=submission,
        entered_name="ZUS RCA",
        document_type=DocumentType.ZUS_RCA_OR_INSURANCE.value,
        position=0,
    )

    # Fetch client with prefetch
    client_prefetched = Client.objects.prefetch_related(
        "wniosek_submissions__attachments",
        "wniosek_submissions__proof_documents",
    ).get(pk=client.pk)

    # Run and count queries
    with CaptureQueriesContext(connection) as ctx:
        summary = build_submitted_document_summary(client_prefetched)
        assert summary["count"] == 1
        assert DocumentType.ZUS_RCA_OR_INSURANCE.value in summary["codes"]

    # It should perform 0 queries because everything was pre-fetched!
    assert len(ctx.captured_queries) == 0


def test_get_document_checklist_requirements_cache(db):
    client = Client.objects.create(first_name="Checklist", last_name="Test", application_purpose="work")
    DocumentRequirement.objects.create(
        application_purpose="work",
        document_type=DocumentType.PASSPORT.value,
        is_required=True,
    )

    # Without cache, it runs queries
    with CaptureQueriesContext(connection) as ctx:
        checklist1 = client.get_document_checklist()
        assert len(checklist1) > 0
    queries_no_cache = len(ctx.captured_queries)

    # With cache, the second call should reuse cached requirements
    cache = {}

    # First call fills cache
    client.get_document_checklist(requirements_cache=cache)

    # Second call should use cache
    with CaptureQueriesContext(connection) as ctx_cached:
        client.get_document_checklist(requirements_cache=cache)

    # The second call should execute significantly fewer queries (specifically, no queries for DocumentRequirement)
    assert len(ctx_cached.captured_queries) < queries_no_cache
