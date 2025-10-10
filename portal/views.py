# portal/views.py (ФИНАЛЬНАЯ ВЕРСИЯ С ЗАЩИТОЙ ОТ ОШИБКИ)

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import RequestDataTooBig
from django.http import JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.template.loader import render_to_string
from django.urls import reverse_lazy
from django.utils.translation import gettext as _
from django.views.generic import DetailView, UpdateView

from clients.models import Client
from clients.forms import DocumentUploadForm
from .forms import ProfileEditForm, ClientApplicationForm
from .models import ClientApplication
from legalize_site.utils.http import request_is_ajax


class ProfileDetailView(LoginRequiredMixin, DetailView):
    model = Client
    template_name = 'portal/profile_detail.html'
    context_object_name = 'client'

    def get_object(self, queryset=None):
        """Возвращает профиль клиента, связанный с текущим пользователем."""
        return get_object_or_404(Client, user=self.request.user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        client = context.get('client') or self.object
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
        return get_object_or_404(Client, user=self.request.user)

def _is_ajax(request):
    """Определяет, является ли запрос AJAX/FETCH, даже если заголовок записан иначе."""
    return (
        request.headers.get('x-requested-with') == 'XMLHttpRequest'
        or request.META.get('HTTP_X_REQUESTED_WITH') == 'XMLHttpRequest'
    )


def _format_upload_limit():
    """Возвращает максимально допустимый размер файла в МБ для отображения пользователю."""
    limit = getattr(settings, 'DATA_UPLOAD_MAX_MEMORY_SIZE', None)
    if not limit:
        return '2.5'

    size_mb = limit / (1024 * 1024)
    if float(size_mb).is_integer():
        return str(int(size_mb))
    return f"{size_mb:.1f}"


def _file_too_large_response(request, wants_json):
    message = _('Размер файла слишком большой. Максимум %(size)s МБ.') % {'size': _format_upload_limit()}

    if wants_json:
        response = JsonResponse({
            'status': 'error',
            'message': message,
            'code': 'file_too_large'
        }, status=413)
        response['Cache-Control'] = 'no-store'
        return response

    messages.error(request, message)
    return redirect('portal:profile_detail')


@login_required
def portal_document_upload(request, doc_type):
    client = get_object_or_404(Client, user=request.user)
    if not client.has_checklist_access:
        return JsonResponse({'status': 'error', 'message': _('Доступ запрещен')}, status=403)

    expects_json = request_is_ajax(request)
    wants_json = _is_ajax(request) or expects_json

    if request.method == 'POST':
        try:
            form = DocumentUploadForm(request.POST, request.FILES)
        except RequestDataTooBig:
            return _file_too_large_response(request, wants_json)

        uploaded_file = request.FILES.get('file')
        max_bytes = getattr(settings, 'DATA_UPLOAD_MAX_MEMORY_SIZE', None)
        if uploaded_file and max_bytes and uploaded_file.size > max_bytes:
            return _file_too_large_response(request, wants_json)

        if form.is_valid():
            document = form.save(commit=False)
            document.client = client
            document.document_type = doc_type
            document.save()

            if wants_json:
                html = render_to_string('portal/partials/document_item.html', {'doc': document}, request=request)
                response = JsonResponse({
                    'status': 'success',
                    'html': html,
                    'doc_id': document.id,
                    'doc_type': doc_type,
                    'message': _('Файл успешно загружен и ожидает проверки.')
                })
                response['Cache-Control'] = 'no-store'
                return response
        else:
            if wants_json:
                response = JsonResponse({'status': 'error', 'errors': form.errors}, status=400)
                response['Cache-Control'] = 'no-store'
                return response

    return redirect('portal:profile_detail')


@login_required
def checklist_status_api(request):
    client = get_object_or_404(Client, user=request.user)
    if not client.has_checklist_access:
        response = JsonResponse({'status': 'no_access', 'message': _('Доступ к чеклисту документов не предоставлен.')})
        response['Cache-Control'] = 'no-store'
        return response

    verification_statuses = {
        str(doc.id): doc.verified
        for doc in client.documents.all()
    }

    response = JsonResponse({'status': 'success', 'statuses': verification_statuses})
    response['Cache-Control'] = 'no-store'
    return response


@login_required
def portal_checklist_partial(request):
    client = get_object_or_404(Client, user=request.user)
    if not client.has_checklist_access:
        response = JsonResponse({'status': 'no_access', 'message': _('Доступ к чеклисту документов не предоставлен.')}, status=403)
        response['Cache-Control'] = 'no-store'
        return response

    document_status_list = client.get_document_checklist()
    html = render_to_string(
        'portal/partials/document_checklist_content.html',
        {'document_status_list': document_status_list},
        request=request
    )

    response = JsonResponse({'status': 'success', 'html': html})
    response['Cache-Control'] = 'no-store'
    return response


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
