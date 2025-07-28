# portal/views.py (ФИНАЛЬНАЯ ВЕРСИЯ С ЗАЩИТОЙ ОТ ОШИБКИ)

from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse_lazy
from django.views.generic import DetailView, UpdateView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse
from django.template.loader import render_to_string
from django.utils.translation import gettext as _
from django.contrib.auth.decorators import login_required

from clients.models import Client
from clients.forms import DocumentUploadForm
from .forms import ProfileEditForm, ClientApplicationForm
from .models import ClientApplication


class ProfileDetailView(LoginRequiredMixin, DetailView):
    model = Client
    template_name = 'portal/profile_detail.html'
    context_object_name = 'client'

    def get_object(self, queryset=None):
        # --- ВОТ ГЛАВНОЕ ИСПРАВЛЕНИЕ ---
        # Эта строка теперь не просто ищет клиента, а создает его, если он не найден.
        # Это решает проблему, если профиль клиента был случайно удален.
        client, created = Client.objects.get_or_create(user=self.request.user)
        return client
        # --------------------------------

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        client = self.get_object()
        if client.has_checklist_access:
            context['document_status_list'] = client.get_document_checklist()

        context['js_messages'] = {
            'no_docs_message': _("Вы еще не загрузили файлы этого типа."),
            'verified_status': _("Проверен"),
            'pending_verification_status': _("Ожидает проверки"),
            'required_status': _("Требуется"),
            'uploaded_status': _("Загружено"),
        }
        return context


class ProfileUpdateView(LoginRequiredMixin, UpdateView):
    model = Client
    form_class = ProfileEditForm
    template_name = 'portal/profile_edit.html'
    success_url = reverse_lazy('portal:profile_detail')

    def get_object(self, queryset=None):
        # Применяем то же исправление и здесь для надежности
        client, created = Client.objects.get_or_create(user=self.request.user)
        return client

@login_required
def portal_document_upload(request, doc_type):
    client = get_object_or_404(Client, user=request.user)
    if not client.has_checklist_access:
        return JsonResponse({'status': 'error', 'message': _('Доступ запрещен')}, status=403)

    if request.method == 'POST':
        form = DocumentUploadForm(request.POST, request.FILES)
        if form.is_valid():
            document = form.save(commit=False)
            document.client = client
            document.document_type = doc_type
            document.save()

            if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                html = render_to_string('portal/partials/document_item.html', {'doc': document}, request=request)
                return JsonResponse({
                    'status': 'success',
                    'html': html,
                    'doc_id': document.id,
                    'doc_type': doc_type,
                    'message': _('Файл успешно загружен и ожидает проверки.')
                })
        else:
            if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                return JsonResponse({'status': 'error', 'errors': form.errors}, status=400)

    return redirect('portal:profile_detail')


@login_required
def checklist_status_api(request):
    client = get_object_or_404(Client, user=request.user)
    if not client.has_checklist_access:
        return JsonResponse({'status': 'no_access', 'message': _('Доступ к чеклисту документов не предоставлен.')})

    verification_statuses = {
        str(doc.id): doc.verified
        for doc in client.documents.all()
    }

    return JsonResponse({'status': 'success', 'statuses': verification_statuses})


@login_required
def client_application_view(request):
    try:
        application = request.user.application
    except ClientApplication.DoesNotExist:
        application = None

    if request.method == 'POST':
        form = ClientApplicationForm(request.POST, request.FILES, instance=application)
        if form.is_valid():
            application_instance = form.save(commit=False)
            application_instance.user = request.user
            application_instance.save()
            # Исправляем редирект, чтобы он использовал пространство имен
            return redirect('portal:application_success')
    else:
        form = ClientApplicationForm(instance=application)

    context = {
        'form': form
    }
    return render(request, 'portal/client_form.html', context)


@login_required
def application_success_view(request):
    # Указываем правильный путь к шаблону
    return render(request, 'portal/application_success.html')