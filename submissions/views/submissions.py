from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.contrib import messages
from django.utils.translation import gettext_lazy as _
from django.http import HttpRequest, HttpResponse, HttpResponseNotAllowed
from django.shortcuts import get_object_or_404, render
from django.views import View
from django.views.generic import ListView, DetailView
from typing import Any

from clients.views.base import StaffRequiredMixin, staff_required_view
from ..models import Submission
from ..forms import SubmissionForm, DocumentForm

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
