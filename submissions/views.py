from __future__ import annotations

import json
from typing import Any

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpRequest, HttpResponse, HttpResponseNotAllowed, JsonResponse
from django.urls import reverse_lazy
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.decorators import method_decorator
from django.utils.translation import gettext_lazy as _
from django.views import View
from django.views.generic import DetailView, ListView

from clients.views.base import StaffRequiredMixin, staff_required_view
from clients.services.responses import ResponseHelper

from .forms import DocumentForm, SubmissionForm
from .models import Document, Submission


class SubmissionListView(StaffRequiredMixin, ListView):
    model = Submission
    template_name = 'submissions/submission_list.html'
    context_object_name = 'submissions'


class SubmissionCreateView(StaffRequiredMixin, View):
    template_name = 'submissions/submission_form.html'

    def get(self, request: HttpRequest) -> HttpResponse:
        form = SubmissionForm()
        return render(request, self.template_name, {'form': form})

    def post(self, request: HttpRequest) -> HttpResponse:
        form = SubmissionForm(request.POST)
        if form.is_valid():
            submission = form.save()
            messages.success(request, _('Основание подачи создано'))
            return redirect('submissions:submission_detail', pk=submission.pk)
        return render(request, self.template_name, {'form': form})


@staff_required_view
def submission_quick_create(request: HttpRequest) -> HttpResponse:
    if request.method != 'POST':
        return HttpResponseNotAllowed(['POST'])

    form = SubmissionForm(request.POST)
    if form.is_valid():
        submission = form.save()
        messages.success(request, _('Основание подачи создано'))
        redirect_url = request.META.get('HTTP_REFERER') or reverse_lazy('clients:document_checklist_manage')
        return redirect(redirect_url)

    messages.error(request, _('Не удалось создать основание'), extra_tags='danger')
    redirect_url = request.META.get('HTTP_REFERER') or reverse_lazy('clients:document_checklist_manage')
    return redirect(redirect_url)


@staff_required_view
def submission_quick_update(request: HttpRequest, submission_id: int) -> HttpResponse:
    submission = get_object_or_404(Submission, pk=submission_id)

    if request.method != 'POST':
        return HttpResponseNotAllowed(['POST'])

    form = SubmissionForm(request.POST, instance=submission)
    redirect_url = request.META.get('HTTP_REFERER') or reverse_lazy('clients:document_checklist_manage')

    if form.is_valid():
        form.save()
        messages.success(request, _('Основание подачи обновлено'))
        return redirect(redirect_url)

    messages.error(request, _('Не удалось обновить основание'), extra_tags='danger')
    return redirect(redirect_url)


@staff_required_view
def submission_quick_delete(request: HttpRequest, submission_id: int) -> HttpResponse:
    if request.method != 'POST':
        return HttpResponseNotAllowed(['POST'])

    submission = get_object_or_404(Submission, pk=submission_id)
    redirect_url = request.META.get('HTTP_REFERER') or reverse_lazy('clients:document_checklist_manage')
    submission.delete()
    messages.success(request, _('Основание подачи удалено'))
    return redirect(redirect_url)


class SubmissionDetailView(StaffRequiredMixin, DetailView):
    model = Submission
    template_name = 'submissions/submission_detail.html'
    context_object_name = 'submission'

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context['documents'] = self.object.documents.all()
        context['document_form'] = DocumentForm()
        return context


class DocumentCreateView(StaffRequiredMixin, View):
    template_name = 'submissions/document_form.html'

    def get_submission(self, submission_id: int) -> Submission:
        return get_object_or_404(Submission, pk=submission_id)

    def get(self, request: HttpRequest, submission_id: int) -> HttpResponse:
        submission = self.get_submission(submission_id)
        form = DocumentForm()
        return render(request, self.template_name, {'form': form, 'submission': submission})

    def post(self, request: HttpRequest, submission_id: int) -> HttpResponse:
        submission = self.get_submission(submission_id)
        form = DocumentForm(request.POST, request.FILES)
        if form.is_valid():
            document = form.save(commit=False)
            document.submission = submission
            document.save()
            messages.success(request, _('Документ создан'))
            return redirect('submissions:submission_detail', pk=submission.pk)
        return render(request, self.template_name, {'form': form, 'submission': submission})


class DocumentUpdateView(StaffRequiredMixin, View):
    template_name = 'submissions/document_form.html'

    def get_object(self, pk: int) -> Document:
        return get_object_or_404(Document, pk=pk)

    def get(self, request: HttpRequest, pk: int) -> HttpResponse:
        document = self.get_object(pk)
        form = DocumentForm(instance=document)
        return render(request, self.template_name, {'form': form, 'submission': document.submission, 'document': document})

    def post(self, request: HttpRequest, pk: int) -> HttpResponse:
        document = self.get_object(pk)
        form = DocumentForm(request.POST, request.FILES, instance=document)
        if form.is_valid():
            form.save()
            messages.success(request, _('Документ обновлён'))
            return redirect('submissions:submission_detail', pk=document.submission.pk)
        return render(request, self.template_name, {'form': form, 'submission': document.submission, 'document': document})


class DocumentDeleteView(StaffRequiredMixin, View):
    def post(self, request: HttpRequest, pk: int) -> HttpResponse:
        document = get_object_or_404(Document, pk=pk)
        submission_pk = document.submission.pk
        document.delete()
        messages.success(request, _('Документ удалён'))
        return redirect('submissions:submission_detail', pk=submission_pk)


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
