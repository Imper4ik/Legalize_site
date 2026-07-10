"""Query-count regression tests for the payment reminder list.

Each payment reminder card reads its related payment (amount_due, service
description) and client. Without an explicit join that is one extra query per
row — a classic N+1. These tests pin rendering to a constant query count that
does not grow with the number of rows, and prove the header counter reflects
the full result set rather than the current page.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from django.db import connection
from django.test import RequestFactory, TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from clients.models import Payment, Reminder
from clients.testing.factories import create_test_client, create_test_user
from clients.views.reminders import PaymentReminderListView


class PaymentReminderQueryCountTests(TestCase):
    def setUp(self) -> None:
        self.staff = create_test_user(role="Staff")
        self.client.force_login(self.staff)
        self.url = reverse("clients:payment_reminder_list")

    def _make_payment_reminders(self, count: int) -> None:
        for idx in range(count):
            client = create_test_client(
                email=f"pay-{idx}-{id(self)}@example.test",
                first_name=f"Payer{idx}",
                last_name="Test",
            )
            case = client.cases.get()
            payment = Payment.objects.create(
                client=client,
                case=case,
                service_description="consultation",
                status="partial",
                total_amount=Decimal("100.00"),
                amount_paid=Decimal("25.00"),
                due_date=date.today(),
            )
            reminder = Reminder.objects.filter(payment=payment).first()
            if reminder is None:
                reminder = Reminder.objects.create(
                    client=client,
                    case=case,
                    payment=payment,
                    due_date=date.today(),
                    reminder_type="payment",
                    title="Payment due",
                    is_active=True,
                )
            elif not reminder.is_active:
                reminder.is_active = True
                reminder.save(update_fields=["is_active"])

    def _render_row_queries(self) -> int:
        """Queries to fetch the page's reminders and render every card field."""
        factory = RequestFactory().get(self.url)
        factory.user = self.staff
        view = PaymentReminderListView()
        view.request = factory
        queryset = view.get_queryset()[: view.paginate_by]
        with CaptureQueriesContext(connection) as ctx:
            for reminder in list(queryset):
                str(reminder.display_title)
                str(reminder.display_notes)
                str(reminder.client)
        return len(ctx.captured_queries)

    def test_row_rendering_query_count_does_not_grow_per_row(self) -> None:
        self._make_payment_reminders(10)
        queries_10 = self._render_row_queries()

        self._make_payment_reminders(40)  # 50 total, one full page
        queries_50 = self._render_row_queries()

        # The heart of the N+1 fix: rendering 5x the rows must not add ~40
        # queries. Fetching + accessing payment/client stays flat.
        self.assertEqual(
            queries_10,
            queries_50,
            msg=f"Row rendering scaled with row count: 10 rows={queries_10}, 50 rows={queries_50}",
        )
        # And the whole page's worth of rows costs only a couple of queries.
        self.assertLessEqual(
            queries_50,
            3,
            msg=f"Rendering 50 payment reminder rows used {queries_50} queries",
        )

    def test_full_page_query_count_stays_bounded_and_flat(self) -> None:
        from django.core.cache import cache

        self._make_payment_reminders(10)
        cache.clear()
        with CaptureQueriesContext(connection) as ctx10:
            self.assertEqual(self.client.get(self.url).status_code, 200)

        self._make_payment_reminders(40)  # 50 total
        cache.clear()
        with CaptureQueriesContext(connection) as ctx50:
            self.assertEqual(self.client.get(self.url).status_code, 200)

        # Adding 40 rows must not add ~40 queries to the rendered page.
        self.assertLessEqual(
            len(ctx50.captured_queries),
            len(ctx10.captured_queries) + 2,
            msg=(
                f"Full page scaled with rows: 10 rows={len(ctx10.captured_queries)}, "
                f"50 rows={len(ctx50.captured_queries)}"
            ),
        )

    def test_counter_reflects_total_not_current_page(self) -> None:
        self._make_payment_reminders(55)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        # Only one page worth of rows is rendered...
        self.assertEqual(len(response.context["reminders"]), 50)
        # ...but the header counter reports the full result set.
        self.assertEqual(response.context["reminders_count"], 55)
