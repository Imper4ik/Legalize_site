from __future__ import annotations

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect
from django.utils import timezone
from django.views.generic import ListView

from clients.forms import StaffTaskForm
from clients.models import Client, StaffTask
from clients.services.access import accessible_clients_queryset, accessible_tasks_queryset
from clients.use_cases.tasks import complete_task_for_client, create_task_for_client
from clients.views.base import StaffRequiredMixin, staff_required_view


class TaskListView(StaffRequiredMixin, ListView):
    model = StaffTask
    template_name = "clients/tasks_list.html"
    context_object_name = "tasks"
    paginate_by = 50

    def get_queryset(self):
        queryset = (
            accessible_tasks_queryset(
                self.request.user,
                StaffTask.objects.select_related("client", "assignee", "created_by")
            )
            .exclude(status__in=["done", "cancelled"])
            .order_by("due_date", "-created_at")
        )
        assignee_filter = self.request.GET.get("assignee")
        if assignee_filter == "me":
            queryset = queryset.filter(assignee=self.request.user)
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        today = timezone.localdate()
        context["overdue_count"] = self.get_queryset().filter(due_date__lt=today).count()
        context["today"] = today
        context["assignee_filter"] = self.request.GET.get("assignee", "")
        return context


@staff_required_view
def add_task(request, client_id):
    client = get_object_or_404(accessible_clients_queryset(request.user, Client.objects.all()), pk=client_id)

    if request.method != "POST":
        return redirect("clients:client_detail", pk=client.pk)

    form = StaffTaskForm(request.POST)
    if form.is_valid():
        create_task_for_client(
            client=client,
            actor=request.user,
            cleaned_data=form.cleaned_data,
        )
        messages.success(request, "Задача создана.")
    else:
        messages.error(request, "Не удалось создать задачу. Проверьте форму.")
    return redirect("clients:client_detail", pk=client.pk)


@staff_required_view
def complete_task(request, task_id):
    task = get_object_or_404(
        accessible_tasks_queryset(request.user, StaffTask.objects.select_related("client")),
        pk=task_id,
    )

    if request.method == "POST":
        result = complete_task_for_client(task=task, actor=request.user)
        if result.completed:
            messages.success(request, "Задача отмечена как выполненная.")

    return redirect("clients:client_detail", pk=task.client.pk)
