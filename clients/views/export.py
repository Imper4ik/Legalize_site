"""Views for exporting client case data (PDF print page + ZIP download)."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.translation import gettext as _
from django.views.generic import DetailView

from clients.models import Client, Document, DocumentVersion
from clients.security.encrypted import safe_encrypted_attr
from clients.services.access import accessible_clients_queryset, accessible_documents_queryset
from clients.services.export import ExportSizeLimitExceeded, generate_client_zip
from clients.services.responses import apply_no_store
from clients.services.roles import EXPORT_MUTATION_ROLES
from clients.use_cases.exports import (
    record_client_export,
    restore_document_version_for_client,
)
from clients.views.base import RoleOrFeatureRequiredMixin, role_or_feature_required_view
from legalize_site.utils.files import build_protected_file_response

if TYPE_CHECKING:
    from django.http.response import HttpResponseBase

logger = logging.getLogger(__name__)


class ClientExportPDFView(RoleOrFeatureRequiredMixin, DetailView):
    allowed_roles = list(EXPORT_MUTATION_ROLES)
    required_permission_name = "can_export_clients"
    """Render a print-optimised HTML page summarising the entire client case."""

    model = Client
    template_name = "clients/client_export_pdf.html"

    def get_queryset(self) -> Any:
        return accessible_clients_queryset(self.request.user, Client.objects.defer("case_number", "passport_num"))

    def get(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        self.object = self.get_object()
        context = self.get_context_data(object=self.object)
        record_client_export(
            client=self.object,
            actor=request.user,
            export_type="pdf_preview",
            summary=_("Экспорт кейса (PDF preview)"),
        )
        response = self.render_to_response(context)
        return apply_no_store(response)

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        client = self.object
        context["documents"] = client.documents.all().order_by("document_type", "-uploaded_at")
        context["payments"] = client.payments.all().order_by("-created_at")
        context["email_logs"] = client.email_logs.all().order_by("-sent_at")[:30]
        context["tasks"] = client.staff_tasks.all().order_by("-created_at")[:30]
        context["reminders"] = client.reminders.filter(is_active=True).order_by("due_date")
        context["activities"] = client.activities.all().order_by("-created_at")[:50]
        context["safe_case_number"] = safe_encrypted_attr(client, "case_number")
        context["generated_at"] = timezone.now()
        return context


@role_or_feature_required_view("can_export_clients", *EXPORT_MUTATION_ROLES)
def client_export_zip(request: HttpRequest, pk: int) -> HttpResponse:
    """Stream a ZIP archive of the full client case as a download."""

    from django.contrib import messages as django_messages

    client = get_object_or_404(accessible_clients_queryset(request.user, Client.objects.defer("case_number", "passport_num")), pk=pk)

    try:
        buffer = generate_client_zip(client)
    except ExportSizeLimitExceeded as exc:
        django_messages.error(
            request,
            _("Экспорт невозможен: суммарный размер файлов клиента (%(total).1f MB) "
              "превышает лимит (%(limit)s MB).") % {"total": exc.total_mb, "limit": exc.limit_mb},
        )
        return redirect("clients:client_detail", pk=pk)

    filename = f"case_{client.pk}.zip"

    record_client_export(
        client=client,
        actor=request.user,
        export_type="zip",
        summary=_("Экспорт кейса (ZIP)"),
        metadata={
            "document_count": client.documents.count(),
            "payment_count": client.payments.count(),
        },
    )

    response = HttpResponse(buffer.getvalue(), content_type="application/zip")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return apply_no_store(response)


@role_or_feature_required_view("can_export_clients", *EXPORT_MUTATION_ROLES)
def document_versions_view(request: HttpRequest, doc_id: int) -> HttpResponse:
    """List all versions of a specific document."""

    document = get_object_or_404(accessible_documents_queryset(request.user, Document.objects.all()), pk=doc_id)
    versions = document.versions.all().order_by("-version_number")
    response = render(
        request,
        "clients/document_versions.html",
        {
            "document": document,
            "client": document.client,
            "versions": versions,
        },
    )
    return apply_no_store(response)


@role_or_feature_required_view("can_export_clients", *EXPORT_MUTATION_ROLES)
def document_version_download(request: HttpRequest, version_id: int) -> HttpResponseBase:
    version = get_object_or_404(
        DocumentVersion.objects.select_related("document", "document__client").filter(
            document__in=accessible_documents_queryset(request.user, Document.objects.all())
        ),
        pk=version_id,
    )
    record_client_export(
        client=version.document.client,
        actor=request.user,
        export_type="document_version_download",
        summary=_("Скачана версия документа"),
        metadata={
            "document_id": version.document_id,
            "document_version_id": version.pk,
            "version_number": version.version_number,
        },
    )

    file_name = str(version.file.name)
    extension = Path(file_name).suffix or ".bin"
    filename = f"document-version-{version.pk}{extension}"
    return build_protected_file_response(version.file, filename=filename, as_attachment=True)


@role_or_feature_required_view("can_export_clients", *EXPORT_MUTATION_ROLES)
def document_version_restore(request: HttpRequest, version_id: int) -> HttpResponse:
    """Restore a previous document version, archiving the current file."""

    from django.contrib import messages

    if request.method != "POST":
        return HttpResponse(status=405)

    version = get_object_or_404(
        DocumentVersion.objects.select_related("document").filter(
            document__in=accessible_documents_queryset(request.user, Document.objects.all())
        ),
        pk=version_id,
    )
    document = version.document

    try:
        result = restore_document_version_for_client(
            version=version,
            actor=request.user,
        )
    except Exception:
        logger.exception("Failed to restore version %s", version.pk)
        messages.error(request, _("Failed to restore this document version."))
        return redirect("clients:document_versions", doc_id=document.pk)

    messages.success(
        request,
        _("Документ восстановлен к версии %(num)s.") % {"num": version.version_number},
    )
    return redirect("clients:client_detail", pk=result.client.pk)


client_export_pdf_view = ClientExportPDFView.as_view()
