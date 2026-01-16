import json
from typing import Any

from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpRequest, JsonResponse
from django.shortcuts import get_object_or_404
from django.utils.decorators import method_decorator
from django.utils.translation import gettext_lazy as _
from django.views import View

from clients.services.responses import ResponseHelper
from clients.views.base import staff_required_view

from ..forms import DocumentForm, SubmissionForm
from ..models import Document, Submission


@method_decorator(login_required, name='dispatch')
class SubmissionApiView(LoginRequiredMixin, View):
    def get(self, request: HttpRequest) -> JsonResponse:
        helper = ResponseHelper(request)
        submissions = Submission.objects.all().values('id', 'name', 'status', 'created_at')
        return helper.success(items=list(submissions))

    def post(self, request: HttpRequest) -> JsonResponse:
        helper = ResponseHelper(request)
        data = self._get_payload(request)
        form = SubmissionForm(data)
        if form.is_valid():
            submission = form.save()
            return helper.success(
                message=_('Основание создано'),
                submission=self._serialize_submission(submission),
            )
        return helper.error(message=_('Ошибка валидации'), errors=form.errors, status=400)

    def _get_payload(self, request: HttpRequest) -> dict[str, Any]:
        if request.content_type and 'application/json' in request.content_type:
            try:
                return json.loads(request.body.decode('utf-8') or '{}')
            except json.JSONDecodeError:
                return {}
        return request.POST.dict()

    def _serialize_submission(self, submission: Submission) -> dict[str, Any]:
        return {
            'id': submission.id,
            'name': submission.name,
            'status': submission.status,
            'created_at': submission.created_at,
        }


@method_decorator(login_required, name='dispatch')
class SubmissionDetailApiView(LoginRequiredMixin, View):
    def get(self, request: HttpRequest, pk: int) -> JsonResponse:
        helper = ResponseHelper(request)
        submission = get_object_or_404(Submission, pk=pk)
        return helper.success(submission=self._serialize(submission))

    def delete(self, request: HttpRequest, pk: int) -> JsonResponse:
        helper = ResponseHelper(request)
        submission = get_object_or_404(Submission, pk=pk)
        submission.delete()
        return helper.success(message=_('Основание удалено'))

    def _serialize(self, submission: Submission) -> dict[str, Any]:
        return {
            'id': submission.id,
            'name': submission.name,
            'status': submission.status,
            'created_at': submission.created_at,
            'documents': [self._serialize_document(doc) for doc in submission.documents.all()],
        }

    def _serialize_document(self, document: Document) -> dict[str, Any]:
        return {
            'id': document.id,
            'submission_id': document.submission_id,
            'title': document.title,
            'status': document.status,
            'file_path': document.file_path.url if document.file_path else None,
            'created_at': document.created_at,
        }


@method_decorator(login_required, name='dispatch')
class DocumentApiView(LoginRequiredMixin, View):
    def get(self, request: HttpRequest, submission_id: int) -> JsonResponse:
        helper = ResponseHelper(request)
        documents = Document.objects.filter(submission_id=submission_id).values(
            'id', 'submission_id', 'title', 'status', 'file_path', 'created_at'
        )
        return helper.success(items=list(documents))

    def post(self, request: HttpRequest, submission_id: int) -> JsonResponse:
        helper = ResponseHelper(request)
        submission = get_object_or_404(Submission, pk=submission_id)
        data = request.POST.dict() if request.method == 'POST' else {}
        if request.content_type and 'application/json' in request.content_type:
            try:
                data = json.loads(request.body.decode('utf-8') or '{}')
            except json.JSONDecodeError:
                data = {}
        form = DocumentForm(data, request.FILES)
        if form.is_valid():
            document = form.save(commit=False)
            document.submission = submission
            document.save()
            return helper.success(
                message=_('Документ создан'),
                document=self._serialize_document(document),
            )
        return helper.error(message=_('Ошибка валидации'), errors=form.errors, status=400)

    def _serialize_document(self, document: Document) -> dict[str, Any]:
        return {
            'id': document.id,
            'submission_id': document.submission_id,
            'title': document.title,
            'status': document.status,
            'file_path': document.file_path.url if document.file_path else None,
            'created_at': document.created_at,
        }


@method_decorator(login_required, name='dispatch')
class DocumentDetailApiView(LoginRequiredMixin, View):
    def put(self, request: HttpRequest, pk: int) -> JsonResponse:
        return self._update(request, pk)

    def patch(self, request: HttpRequest, pk: int) -> JsonResponse:
        return self._update(request, pk)

    def delete(self, request: HttpRequest, pk: int) -> JsonResponse:
        helper = ResponseHelper(request)
        document = get_object_or_404(Document, pk=pk)
        document.delete()
        return helper.success(message=_('Документ удалён'))

    def _update(self, request: HttpRequest, pk: int) -> JsonResponse:
        helper = ResponseHelper(request)
        document = get_object_or_404(Document, pk=pk)
        data: dict[str, Any] = {}
        files = None
        if request.content_type and 'application/json' in request.content_type:
            try:
                data = json.loads(request.body.decode('utf-8') or '{}')
            except json.JSONDecodeError:
                data = {}
        else:
            data = request.POST.dict()
            files = request.FILES
        form_data = {
            'title': data.get('title', document.title),
            'status': data.get('status', document.status),
        }

        if 'file_path' in data:
            form_data['file_path'] = data['file_path']
        form = DocumentForm(form_data, files, instance=document)
        if form.is_valid():
            form.save()
            return helper.success(
                message=_('Документ обновлён'),
                document={
                    'id': document.id,
                    'submission_id': document.submission_id,
                    'title': document.title,
                    'status': document.status,
                    'file_path': document.file_path.url if document.file_path else None,
                    'created_at': document.created_at,
                },
            )
        return helper.error(message=_('Ошибка валидации'), errors=form.errors, status=400)


submission_api = staff_required_view(SubmissionApiView.as_view())
submission_detail_api = staff_required_view(SubmissionDetailApiView.as_view())
document_api = staff_required_view(DocumentApiView.as_view())
document_detail_api = staff_required_view(DocumentDetailApiView.as_view())
