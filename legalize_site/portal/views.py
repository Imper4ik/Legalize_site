from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.urls import reverse_lazy
from django.views.generic import DetailView, UpdateView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse
from django.template.loader import render_to_string

from clients.models import Client, Document
from clients.forms import DocumentUploadForm
from .forms import ProfileEditForm


class ProfileDetailView(LoginRequiredMixin, DetailView):
    model = Client
    template_name = 'portal/profile_detail.html'
    context_object_name = 'client'

    def get_object(self, queryset=None):
        return Client.objects.get(user=self.request.user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        client = self.get_object()
        if client.has_checklist_access:
            context['document_status_list'] = client.get_document_checklist()
        return context


class ProfileUpdateView(LoginRequiredMixin, UpdateView):
    model = Client
    form_class = ProfileEditForm
    template_name = 'portal/profile_edit.html'
    success_url = reverse_lazy('portal:profile_detail')

    def get_object(self, queryset=None):
        return Client.objects.get(user=self.request.user)


@login_required
def portal_document_upload(request, doc_type):
    client = get_object_or_404(Client, user=request.user)
    if not client.has_checklist_access:
        return JsonResponse({'status': 'error', 'message': 'Доступ запрещен'}, status=403)

    if request.method == 'POST':
        form = DocumentUploadForm(request.POST, request.FILES)
        if form.is_valid():
            document = form.save(commit=False)
            document.client = client
            document.document_type = doc_type
            document.save()

            if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                html = render_to_string('portal/partials/document_item.html', {'doc': document})
                return JsonResponse({
                    'status': 'success',
                    'html': html,
                    'doc_type': doc_type,
                    'message': 'Файл успешно загружен и ожидает проверки.'
                })
        else:
            if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                return JsonResponse({'status': 'error', 'errors': form.errors.as_json()}, status=400)

    return redirect('portal:profile_detail')


@login_required
def checklist_status_api(request):
    """
    Возвращает статусы верификации и ID существующих документов клиента.
    """
    client = get_object_or_404(Client, user=request.user)
    if not client.has_checklist_access:
        return JsonResponse({'status': 'no_access'})

    # Создаем словарь: {id_документа: True/False}
    verification_statuses = {
        doc.id: doc.verified
        for doc in client.documents.all()
    }

    return JsonResponse({'status': 'success', 'statuses': verification_statuses})