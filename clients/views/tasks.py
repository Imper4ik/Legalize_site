from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from django.contrib import messages
from django.http import HttpRequest
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _
from django.views.generic import ListView

from clients.forms import StaffTaskForm
from clients.models import Client, StaffTask
from clients.services.access import accessible_clients_queryset, accessible_tasks_queryset
from clients.views.base import safe_redirect_target
from clients.services.roles import TASK_MUTATION_ROLES
from clients.use_cases.tasks import complete_task_for_client, create_task_for_client
from clients.views.base import RoleOrFeatureRequiredMixin, role_or_feature_required_view

if TYPE_CHECKING:
    from django.http.response import HttpResponseBase


class TaskListView(RoleOrFeatureRequiredMixin, ListView):
    model = StaffTask
    allowed_roles = list(TASK_MUTATION_ROLES)
    required_permission_name = "can_manage_staff_tasks"
    template_name = "clients/tasks_list.html"
    context_object_name = "tasks"
    paginate_by = 50

    def get_queryset(self) -> Any:
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
            queryset = queryset.filter(assignee=cast(Any, self.request.user))
        if self.request.GET.get("type") == "questions":
            queryset = queryset.filter(description__startswith="Клиент задал вопрос через приложение:")
        return queryset

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        today = timezone.localdate()
        context["overdue_count"] = self.get_queryset().filter(due_date__lt=today).count()
        context["today"] = today
        context["assignee_filter"] = self.request.GET.get("assignee", "")
        context["type_filter"] = self.request.GET.get("type", "")
        return context


@role_or_feature_required_view("can_manage_staff_tasks", *TASK_MUTATION_ROLES)
def add_task(request: HttpRequest, client_id: int) -> HttpResponseBase:
    client = get_object_or_404(accessible_clients_queryset(request.user, Client.objects.all()), pk=client_id)

    if request.method != "POST":
        return redirect("clients:client_detail", pk=client.pk)

    form = StaffTaskForm(request.POST, client=client)
    if form.is_valid():
        create_task_for_client(
            client=client,
            actor=request.user,
            cleaned_data=form.cleaned_data,
        )
        messages.success(request, _("Задача создана."))
    else:
        messages.error(request, _("Не удалось создать задачу. Проверьте форму."))
    return redirect(safe_redirect_target(request) or reverse("clients:client_detail", kwargs={"pk": client.pk}))


@role_or_feature_required_view("can_manage_staff_tasks", *TASK_MUTATION_ROLES)
def complete_task(request: HttpRequest, task_id: int) -> HttpResponseBase:
    task = get_object_or_404(
        accessible_tasks_queryset(request.user, StaffTask.objects.select_related("client")),
        pk=task_id,
    )

    if request.method == "POST":
        result = complete_task_for_client(task=task, actor=request.user)
        if result.completed:
            messages.success(request, _("Задача отмечена как выполненная."))

    return redirect(safe_redirect_target(request) or reverse("clients:client_detail", kwargs={"pk": task.client.pk}))
