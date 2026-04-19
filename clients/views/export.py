"""Views for exporting client case data (PDF print page + ZIP download)."""

from __future__ import annotations

import logging

from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.views.generic import DetailView

from clients.models import Client, Document, DocumentVersion
from clients.services.activity import log_client_activity
from clients.services.export import generate_client_zip
from clients.views.base import StaffRequiredMixin, staff_required_view

logger = logging.getLogger(__name__)


class ClientExportPDFView(StaffRequiredMixin, DetailView):
    """Render a print-optimised HTML page summarising the entire client case."""

    model = Client
    template_name = "clients/client_export_pdf.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        client = self.object
        context["documents"] = client.documents.all().order_by("document_type", "-uploaded_at")
        context["payments"] = client.payments.all().order_by("-created_at")
        context["email_logs"] = client.email_logs.all().order_by("-sent_at")[:30]
        context["tasks"] = client.staff_tasks.all().order_by("-created_at")[:30]
        context["reminders"] = client.reminders.filter(is_active=True).order_by("due_date")
        context["activities"] = client.activities.all().order_by("-created_at")[:50]
        context["generated_at"] = timezone.now()
        return context


@staff_required_view
def client_export_zip(request, pk):
    """Stream a ZIP archive of the full client case as a download."""

    client = get_object_or_404(Client, pk=pk)
    buffer = generate_client_zip(client)

    safe_name = f"{client.first_name}_{client.last_name}".replace(" ", "_")[:50]
    filename = f"case_{safe_name}_{client.pk}.zip"

    log_client_activity(
        client=client,
        actor=request.user,
        event_type="client_updated",
        summary="Экспорт кейса (ZIP)",
        metadata={"export_type": "zip"},
    )

    response = HttpResponse(buffer.getvalue(), content_type="application/zip")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


@staff_required_view
def document_versions_view(request, doc_id):
    """List all versions of a specific document."""

    from django.shortcuts import render

    document = get_object_or_404(Document, pk=doc_id)
    versions = document.versions.all().order_by("-version_number")
    return render(request, "clients/document_versions.html", {
        "document": document,
        "client": document.client,
        "versions": versions,
    })


@staff_required_view
def document_version_restore(request, version_id):
    """Restore a previous document version, archiving the current file."""

    from django.contrib import messages
    from django.core.files.base import ContentFile
    from django.shortcuts import redirect
    from django.utils.translation import gettext as _

    if request.method != "POST":
        return HttpResponse(status=405)

    version = get_object_or_404(DocumentVersion.objects.select_related("document"), pk=version_id)
    document = version.document

    # Archive current file as a new version
    if document.file:
        current_max = document.versions.aggregate(
            max_v=__import__("django.db.models", fromlist=["Max"]).Max("version_number")
        )["max_v"] or 0

        DocumentVersion.objects.create(
            document=document,
            file=document.file,
            version_number=current_max + 1,
            uploaded_by=request.user,
            comment=_("Автоматическая архивация перед откатом к v%(num)s") % {"num": version.version_number},
            file_name=document.file.name.split("/")[-1] if document.file else "",
            file_size=document.file.size if document.file else 0,
        )

    # Restore the selected version's file
    try:
        restored_content = version.file.read()
        ext = version.file.name.split(".")[-1] if "." in version.file.name else "bin"
        new_name = f"documents/restored_{document.pk}.{ext}"
        document.file.save(new_name, ContentFile(restored_content), save=True)
    except Exception:
        logger.exception("Failed to restore version %s", version.pk)
        messages.error(request, _("Не удалось откатить версию."))
        return redirect("clients:document_versions", doc_id=document.pk)

    log_client_activity(
        client=document.client,
        actor=request.user,
        event_type="document_uploaded",
        summary=f"Документ откачен к v{version.version_number}",
        document=document,
    )

    messages.success(
        request,
        _("Документ откачен к версии %(num)s.") % {"num": version.version_number},
    )
    return redirect("clients:client_detail", pk=document.client.pk)


client_export_pdf_view = ClientExportPDFView.as_view()
