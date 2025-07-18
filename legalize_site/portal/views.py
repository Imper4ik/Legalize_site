from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse_lazy
from django.views.generic import DetailView, UpdateView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages
from clients.models import Client, Payment, Document
from clients.constants import DOCUMENT_CHECKLIST
from .forms import ProfileEditForm, DocumentPortalUploadForm
from collections import defaultdict


# --- ПРЕДСТАВЛЕНИЯ ДЛЯ ЛИЧНОГО КАБИНЕТА КЛИЕНТА (на основе классов) ---

class ProfileDetailView(LoginRequiredMixin, DetailView):
    model = Client
    template_name = 'portal/profile_detail.html'
    context_object_name = 'profile'

    def get_object(self, queryset=None):
        """Возвращает профиль клиента, связанный с текущим пользователем."""
        profile, created = Client.objects.get_or_create(
            user=self.request.user,
            defaults={'email': self.request.user.email}
        )
        return profile

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        client_profile = self.get_object()

        # Загружаем платежи
        context['payments'] = Payment.objects.filter(client=client_profile).order_by('-created_at')

        # Формируем чеклист документов
        document_status_list = []
        if client_profile.status != 'new':
            checklist_key = (client_profile.application_purpose, client_profile.language)
            required_docs_list = DOCUMENT_CHECKLIST.get(checklist_key, [])
            uploaded_docs = {doc.document_type: doc for doc in client_profile.documents.all()}
            for doc_code, doc_name in required_docs_list:
                document_status_list.append({
                    'code': doc_code,
                    'name': doc_name,
                    'uploaded_doc': uploaded_docs.get(doc_code),
                    'form': DocumentPortalUploadForm()
                })
        context['document_status_list'] = document_status_list
        return context


class ProfileUpdateView(LoginRequiredMixin, UpdateView):
    model = Client
    form_class = ProfileEditForm
    template_name = 'portal/profile_edit.html'
    success_url = reverse_lazy('portal:profile_detail')

    def get_object(self, queryset=None):
        """Возвращает профиль клиента для редактирования."""
        return get_object_or_404(Client, user=self.request.user)

    def form_valid(self, form):
        """При сохранении формы также обновляем данные в стандартной модели User."""
        user = self.request.user
        user.first_name = form.cleaned_data['first_name']
        user.last_name = form.cleaned_data['last_name']
        user.email = form.cleaned_data['email']
        user.save()
        messages.success(self.request, 'Ваш профиль был успешно обновлен!')
        return super().form_valid(form)


# --- Обработчик загрузки документов (остается функцией) ---
@login_required
def document_upload(request, doc_type):
    client = get_object_or_404(Client, user=request.user)
    if request.method == 'POST':
        form = DocumentPortalUploadForm(request.POST, request.FILES)
        if form.is_valid():
            Document.objects.filter(client=client, document_type=doc_type).delete()
            document = form.save(commit=False)
            document.client = client
            document.document_type = doc_type
            document.save()
            messages.success(request, f"Документ '{document.get_document_type_display()}' успешно загружен.")
        else:
            messages.error(request, "Ошибка при загрузке файла. Пожалуйста, попробуйте снова.")
    return redirect('portal:profile_detail')
