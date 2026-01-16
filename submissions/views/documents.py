from django.shortcuts import redirect
from django.contrib import messages
from django.utils.translation import gettext_lazy as _
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, render
from django.views import View

from clients.views.base import StaffRequiredMixin
from ..models import Document, Submission
from ..forms import DocumentForm

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
