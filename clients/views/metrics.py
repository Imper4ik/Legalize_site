from django.shortcuts import render
from django.db.models import Count, Q
from django.utils import timezone
from datetime import timedelta

from clients.models import Client, Document, Payment
from clients.views.base import StaffRequiredMixin
from django.views.generic import TemplateView

class MetricsDashboardView(StaffRequiredMixin, TemplateView):
    template_name = 'clients/metrics_dashboard.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Last 30 days default
        end_date = timezone.localdate()
        start_date = end_date - timedelta(days=30)
        
        # 1. Заведено клиентов за период
        clients_created = Client.objects.filter(created_at__date__gte=start_date, created_at__date__lte=end_date).count()
        
        # 2. Из них загрузили документы
        # Находим клиентов созданных в этот период, у которых есть хотя бы один загруженный документ
        clients_with_docs = Client.objects.filter(
            created_at__date__gte=start_date, 
            created_at__date__lte=end_date,
            documents__isnull=False
        ).distinct().count()
        
        # 3. Созданы платежи
        clients_with_payments = Client.objects.filter(
            created_at__date__gte=start_date, 
            created_at__date__lte=end_date,
            payments__isnull=False
        ).distinct().count()
        
        # 4. Совершена оплата
        clients_paid = Client.objects.filter(
            created_at__date__gte=start_date, 
            created_at__date__lte=end_date,
            payments__status='paid' # assuming 'paid' or similar status
        ).distinct().count()
        
        # 5. Кейс закрыт / Решение получено
        # Assuming decision_date is set or logic dictates closure
        cases_closed = Client.objects.filter(
            created_at__date__gte=start_date, 
            created_at__date__lte=end_date,
            decision_date__isnull=False
        ).distinct().count()

        # Просроченные SLA
        overdue_sla = Client.objects.filter(
            decision_date__lt=end_date,
            # We can define "closed" properly if there is a status field, 
            # for now let's just count total with past decision_dates to check SLA.
        ).count()

        context.update({
            'start_date': start_date,
            'end_date': end_date,
            'funnel': {
                'clients_created': clients_created,
                'clients_with_docs': clients_with_docs,
                'clients_with_payments': clients_with_payments,
                'clients_paid': clients_paid,
                'cases_closed': cases_closed,
            },
            'overdue_sla': overdue_sla
        })
        
        return context
