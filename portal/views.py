from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.urls import reverse_lazy
from django.views.generic import DetailView, UpdateView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse
from django.template.loader import render_to_string
from django.utils.translation import gettext as _  # Импортируем для _()

from clients.models import Client, Document
from clients.forms import DocumentUploadForm
from .forms import ProfileEditForm, ClientApplicationForm
from django.utils import translation
from django.urls import resolve, reverse

from .models import ClientApplication


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

        # --- ADDED: Pass all necessary translated strings to the JavaScript context ---
        context['js_messages'] = {
            'no_docs_message': _("Вы еще не загрузили файлы этого типа."),
            'verified_status': _("Проверен"),
            'pending_verification_status': _("Ожидает проверки"),
            'required_status': _("Требуется"),
            'uploaded_status': _("Загружено"),
        }
        # --------------------------------------------------------------------------
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
        # Улучшенное сообщение об ошибке для AJAX
        return JsonResponse({'status': 'error', 'message': _('Доступ запрещен')}, status=403)

    if request.method == 'POST':
        form = DocumentUploadForm(request.POST, request.FILES)
        if form.is_valid():
            document = form.save(commit=False)
            document.client = client
            document.document_type = doc_type
            document.save()

            if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                # --- ВАЖНО: Убедитесь, что 'portal/partials/document_item.html' рендерит ОДИН LI-ЭЛЕМЕНТ ---
                html = render_to_string('portal/partials/document_item.html', {'doc': document}, request=request)
                return JsonResponse({
                    'status': 'success',
                    'html': html,
                    'doc_id': document.id,  # Добавим ID для удобства
                    'doc_type': doc_type,
                    'message': _('Файл успешно загружен и ожидает проверки.')
                })
        else:
            if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                # Возвращаем ошибки формы в виде словаря, а не строки JSON
                # JS будет легче обработать объект data.errors
                return JsonResponse({'status': 'error', 'errors': form.errors}, status=400)

    # Если это не AJAX-запрос или метод не POST (что маловероятно для этой точки)
    return redirect('portal:profile_detail')


@login_required
def checklist_status_api(request):
    """
    Возвращает статусы верификации и ID существующих документов клиента.
    Для более "живого" обновления, можно было бы возвращать полный HTML обновленных списков документов
    или HTML новых документов, но это усложнит API.
    Текущая логика в JS обновляет и удаляет элементы на основе этих статусов.
    """
    client = get_object_or_404(Client, user=request.user)
    if not client.has_checklist_access:
        return JsonResponse({'status': 'no_access', 'message': _('Доступ к чеклисту документов не предоставлен.')})

    # Создаем словарь: {id_документа (строка): True/False}
    # Преобразуем ID в строку, так как JS получает их как строки из data-doc-id
    verification_statuses = {
        str(doc.id): doc.verified
        for doc in client.documents.all()
    }

    return JsonResponse({'status': 'success', 'statuses': verification_statuses})

@login_required
def client_application_view(request):
    # Проверяем, есть ли у пользователя уже заявка, чтобы не создавать новую
    try:
        application = request.user.application
    except ClientApplication.DoesNotExist:
        application = None

    if request.method == 'POST':
        # Если заявка уже есть, обновляем ее. Если нет - создаем.
        form = ClientApplicationForm(request.POST, request.FILES, instance=application)
        if form.is_valid():
            # Привязываем заявку к текущему пользователю перед сохранением
            application_instance = form.save(commit=False)
            application_instance.user = request.user
            application_instance.save()
            # Перенаправляем на страницу успеха
            return redirect('application_success')
    else:
        # Показываем пустую форму или заполненную, если данные уже есть
        form = ClientApplicationForm(instance=application)

    context = {
        'form': form
    }
    return render(request, 'portal/client_form.html', context)

# Простая страница "успеха"
@login_required
def application_success_view(request):
    return render(request, 'portal/application_success.html')