from __future__ import annotations

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect
from django.utils import timezone
from django.views.generic import ListView

from clients.forms import StaffTaskForm
from clients.models import Client, StaffTask
from clients.services.activity import log_client_activity
from clients.views.base import StaffRequiredMixin, staff_required_view


class TaskListView(StaffRequiredMixin, ListView):
    model = StaffTask
    template_name = "clients/tasks_list.html"
    context_object_name = "tasks"
    paginate_by = 50

    def get_queryset(self):
        queryset = (
            StaffTask.objects.select_related("client", "assignee", "created_by")
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
    client = get_object_or_404(Client, pk=client_id)

    if request.method != "POST":
        return redirect("clients:client_detail", pk=client.pk)

    form = StaffTaskForm(request.POST)
    if form.is_valid():
        task = form.save(commit=False)
        task.client = client
        task.created_by = request.user
        if task.assignee_id is None:
            task.assignee = request.user
        task.save()
        log_client_activity(
            client=client,
            actor=request.user,
            event_type="task_created",
            summary=f"Создана задача: {task.title}",
            details=task.description,
            metadata={
                "priority": task.priority,
                "status": task.status,
                "assignee_id": task.assignee_id,
                "due_date": task.due_date.isoformat() if task.due_date else "",
            },
            task=task,
        )
        messages.success(request, "Задача создана.")
    else:
        messages.error(request, "Не удалось создать задачу. Проверьте форму.")
    return redirect("clients:client_detail", pk=client.pk)


@staff_required_view
def complete_task(request, task_id):
    task = get_object_or_404(StaffTask.objects.select_related("client"), pk=task_id)

    if request.method == "POST" and task.status != "done":
        task.mark_done()
        log_client_activity(
            client=task.client,
            actor=request.user,
            event_type="task_completed",
            summary=f"Задача завершена: {task.title}",
            metadata={"task_id": task.pk},
            task=task,
        )
        messages.success(request, "Задача отмечена как выполненная.")

    return redirect("clients:client_detail", pk=task.client.pk)
