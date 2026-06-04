from clients.views.base import StaffRequiredMixin, staff_required_view
from clients.views.client_crud import ClientCreateView, ClientDeleteView, ClientDetailView, ClientListView, ClientUpdateView, calculator_view, dashboard_redirect_view, client_autocomplete_api
from clients.views.print_views import client_print_view, client_document_print_view, client_document_print_confirm_view, client_wsc_print_view
from clients.views.admin_settings import AdminPanelView, AppSettingsUpdateView, DocumentTemplateHubView, service_price_manage_view, submission_manage_view
from clients.views.staff_views import staff_manage_view, role_manage_view
from clients.views.checklist_views import DocumentChecklistManageView, document_requirement_add, document_requirement_edit, document_requirement_delete
from clients.views.documents import add_client_document_requirement, add_document, client_checklist_partial, client_overview_partial, client_status_api, confirm_wezwanie_parse, document_preview, document_download, document_delete, wniosek_attachment_delete, toggle_document_verification, verify_all_documents, update_client_notes, get_document_parsed_data
from clients.views.emails import email_preview_api, send_custom_email, mass_email_view, campaign_status_api
from clients.views.payments import add_payment, delete_payment, edit_payment, get_price_for_service
from clients.views.tasks import TaskListView, add_task, complete_task
from clients.views.reminders import DocumentReminderListView, PaymentReminderListView, reminder_action, run_update_reminders, send_document_reminder_email
from clients.views.metrics import MetricsDashboardView
from clients.views.family import FamilyDashboardView
from clients.views.admin_dashboard import AdminDashboardView
from clients.views.schedule_views import fingerprints_schedule_view
from clients.views.archive import restore_client_view, restore_document_view, restore_payment_view
from clients.views.export import client_export_pdf_view, client_export_zip, document_version_download, document_versions_view, document_version_restore
from clients.views.logs import EmailLogsView, StaffActivityLogsView
from clients.views.admin_mos_review import admin_mos_review
from clients.views.onboarding_start_contact import onboarding_start_contact as onboarding_start
from clients.views.onboarding_views import (
    check_onboarding_session,
    onboarding_purpose,
    onboarding_document_upload,
    onboarding_document_preview,
    onboarding_document_delete,
    onboarding_digital_access,
    onboarding_personal_data,
    onboarding_passport,
    onboarding_personal_extra,
    onboarding_address,
    onboarding_travel,
    onboarding_declarations,
    onboarding_review,
    generate_onboarding_link,
    quick_create_client_onboarding,
    onboarding_auto_save,
    onboarding_set_password,
)

__all__ = [name for name in globals() if not name.startswith('_')]
