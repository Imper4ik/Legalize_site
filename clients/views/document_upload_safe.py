from __future__ import annotations

from typing import TYPE_CHECKING

from django.contrib import messages
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext as _

from clients.constants import DocumentType
from clients.forms import DocumentUploadForm
from clients.models import Client, ClientDocumentRequirement, Document
from clients.services.access import accessible_clients_queryset
from clients.services.cases import resolve_single_active_case
from clients.services.custom_document_requirements import sync_custom_document_requirement_reminder
from clients.services.notifications import (
    send_appointment_notification_email,
    send_missing_documents_email,
)
from clients.services.responses import ResponseHelper
from clients.services.roles import DOCUMENT_EDIT_ROLES
from clients.views import documents as documents_module
from clients.views.base import role_required_view

if TYPE_CHECKING:
    from django.http import HttpRequest
    from django.http.response import HttpResponseBase


@role_required_view(*DOCUMENT_EDIT_ROLES)
def add_document(request: HttpRequest, client_id: int, doc_type: str) -> HttpResponseBase:
    """Upload documents atomically and clean up only storage-committed files.

    ``FieldFile.name`` contains the client-supplied name before Django writes the
    file. Therefore rollback cleanup must never call storage deletion unless
    ``FieldFile._committed`` is true; otherwise an unrelated existing object with
    the same name could be removed after an early save failure.
    """

    client = get_object_or_404(
        accessible_clients_queryset(request.user, Client.objects.all()),
        pk=client_id,
    )
    document_type_display = client.get_document_name_by_code(doc_type)
    helper = ResponseHelper(request)

    if request.method == "POST":
        parse_requested = request.POST.get("parse_wezwanie") == "1"
        if parse_requested and not documents_module._can_run_ocr_review(request.user):
            return helper.forbidden()

        from clients.services.cases import resolve_active_case_for_client

        case_uuid = request.POST.get("case_uuid")
        case = (
            resolve_active_case_for_client(client, case_uuid)
            if case_uuid
            else resolve_single_active_case(client)
        )
        if case is None:
            message = _("Для этой операции необходимо выбрать дело.")
            if case_uuid:
                message = _("Дело не найдено.")
            if helper.expects_json:
                return helper.error(message=str(message))
            messages.error(request, message)
            return redirect("clients:client_detail", pk=client.id)

        files = request.FILES.getlist("file")
        if not files:
            form = DocumentUploadForm(
                request.POST,
                request.FILES,
                doc_type=doc_type,
                client=client,
                case=case,
            )
            form_errors = form.errors.get_json_data()
            documents_module.logger.warning(
                "Document upload rejected: client_id=%s doc_type=%s errors=%s files=%s",
                client.pk,
                doc_type,
                form_errors,
                documents_module._uploaded_file_log_payload(files),
            )
            if helper.expects_json:
                return helper.error(
                    message=str(_("Проверьте правильность заполнения формы.")),
                    errors=form_errors,
                )
            return redirect("clients:client_detail", pk=client.id)

        if doc_type == DocumentType.ZUS_RCA_OR_INSURANCE.value and len(files) > 1:
            message = _("ZUS RCA can be uploaded only one month at a time.")
            documents_module.logger.warning(
                "Document upload rejected: client_id=%s doc_type=%s reason=multiple_zus_files files=%s",
                client.pk,
                doc_type,
                documents_module._uploaded_file_log_payload(files),
            )
            if helper.expects_json:
                return helper.error(
                    message=str(message),
                    errors={"file": [{"message": str(message)}]},
                )
            messages.error(request, message)
            return redirect("clients:client_detail", pk=client.id)

        validated_forms: list[DocumentUploadForm] = []
        errors: dict = {}
        for uploaded_file in files:
            form = DocumentUploadForm(
                request.POST,
                {"file": uploaded_file},
                doc_type=doc_type,
                client=client,
                case=case,
            )
            if not form.is_valid():
                errors = form.errors.get_json_data()
                documents_module.logger.warning(
                    "Document upload rejected: client_id=%s doc_type=%s errors=%s files=%s",
                    client.pk,
                    doc_type,
                    errors,
                    documents_module._uploaded_file_log_payload([uploaded_file]),
                )
                break
            validated_forms.append(form)

        upload_results = []
        success_count = 0
        if not errors and validated_forms:
            pending_documents: list[Document] = []
            try:
                with transaction.atomic():
                    for form in validated_forms:
                        pending_document = form.save(commit=False)
                        pending_documents.append(pending_document)
                        result = documents_module.upload_client_document(
                            client=client,
                            doc_type=doc_type,
                            uploaded_document=pending_document,
                            actor=request.user,
                            case=case,
                            parse_requested=parse_requested,
                            parser=documents_module.parse_wezwanie,
                            send_missing_email=send_missing_documents_email,
                            send_appointment_email=send_appointment_notification_email,
                        )
                        upload_results.append(result)
                        success_count += 1
            except Exception:
                for pending_document in pending_documents:
                    saved_file = getattr(pending_document, "file", None)
                    if not saved_file or not getattr(saved_file, "_committed", False):
                        continue
                    name = getattr(saved_file, "name", "")
                    if not name:
                        continue
                    try:
                        if saved_file.storage.exists(name):
                            saved_file.delete(save=False)
                    except Exception:
                        documents_module.logger.warning(
                            "Failed to remove orphaned upload after rollback: client_id=%s name=%s",
                            client.pk,
                            name,
                            exc_info=True,
                        )
                raise

        if success_count > 0 and success_count == len(files):
            custom_requirement = ClientDocumentRequirement.objects.filter(
                client=client,
                document_type=doc_type,
                is_active=True,
            ).first()
            if custom_requirement:
                sync_custom_document_requirement_reminder(custom_requirement)

            last_result = upload_results[-1]
            if helper.expects_json:
                primary_result = next(
                    (item for item in upload_results if item.pending_confirmation),
                    last_result,
                )
                documents_payload = [
                    {
                        "doc_id": item.document.id,
                        "manual_review_required": item.manual_review_required,
                        "pending_confirmation": item.pending_confirmation,
                        "ocr_processing_queued": item.ocr_processing_queued,
                        "parsed": item.parsed_payload,
                    }
                    for item in upload_results
                ]
                message = (
                    str(_("Загружено документов: %(count)s") % {"count": success_count})
                    if success_count > 1
                    else last_result.message
                )
                return helper.success(
                    message=message,
                    doc_id=primary_result.document.id,
                    manual_review_required=primary_result.manual_review_required,
                    pending_confirmation=primary_result.pending_confirmation,
                    ocr_processing_queued=primary_result.ocr_processing_queued,
                    parsed=primary_result.parsed_payload,
                    documents=documents_payload,
                )

            if last_result.manual_review_required:
                messages.warning(request, last_result.message)
            else:
                message = (
                    _("Загружено документов: %(count)s") % {"count": success_count}
                    if success_count > 1
                    else last_result.message
                )
                messages.success(request, message)
            return redirect("clients:client_detail", pk=client.id)

        if helper.expects_json:
            return helper.error(
                message=str(_("Проверьте правильность заполнения формы.")),
                errors=errors,
            )

    form = DocumentUploadForm(doc_type=doc_type, client=client)
    return render(
        request,
        "clients/add_document.html",
        {
            "form": form,
            "client": client,
            "doc_type": doc_type,
            "document_type_display": document_type_display,
        },
    )
