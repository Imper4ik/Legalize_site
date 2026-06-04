from clients.views.base import StaffRequiredMixin, staff_required_view
from clients.views.client_crud import *  # noqa: F403
from clients.views.print_views import *  # noqa: F403
from clients.views.admin_settings import *  # noqa: F403
from clients.views.staff_views import *  # noqa: F403
from clients.views.checklist_views import *  # noqa: F403
from clients.views.documents import *  # noqa: F403
from clients.views.emails import *  # noqa: F403
from clients.views.payments import *  # noqa: F403
from clients.views.tasks import *  # noqa: F403
from clients.views.reminders import *  # noqa: F403
from clients.views.metrics import MetricsDashboardView
from clients.views.family import FamilyDashboardView
from clients.views.admin_dashboard import AdminDashboardView
from clients.views.schedule_views import fingerprints_schedule_view
from clients.views.archive import *  # noqa: F403
from clients.views.export import *  # noqa: F403
from clients.views.logs import EmailLogsView, StaffActivityLogsView
from clients.views.admin_mos_review import admin_mos_review
from clients.views.onboarding_token_access import enable_token_link_access
from clients.views.onboarding_start_contact import onboarding_start_contact as onboarding_start
from clients.views.onboarding_views import (
    check_onboarding_session,
    onboarding_purpose,
    onboarding_document_upload,
    onboarding_document_preview,
    onboarding_document_delete,
    onboarding_personal_data,
    onboarding_review,
    generate_onboarding_link,
    quick_create_client_onboarding,
    onboarding_auto_save,
    onboarding_set_password,
)
from clients.views.onboarding_step_return import (
    onboarding_digital_access,
    onboarding_passport,
    onboarding_personal_extra,
    onboarding_address,
    onboarding_travel,
    onboarding_declarations,
)

enable_token_link_access()

__all__ = [name for name in globals() if not name.startswith('_')]
