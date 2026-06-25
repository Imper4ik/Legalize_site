from clients.views.admin_dashboard import AdminDashboardView
from clients.views.admin_mos_review import admin_mos_review
from clients.views.admin_settings import *  # noqa: F403
from clients.views.archive import *  # noqa: F403
from clients.views.base import StaffRequiredMixin, staff_required_view
from clients.views.cases import *  # noqa: F403
from clients.views.checklist_views import *  # noqa: F403
from clients.views.client_crud import *  # noqa: F403
from clients.views.demo_center import democenter_view
from clients.views.documents import *  # noqa: F403
from clients.views.emails import *  # noqa: F403
from clients.views.export import *  # noqa: F403
from clients.views.family import FamilyDashboardView
from clients.views.logs import EmailLogsView, StaffActivityLogsView
from clients.views.metrics import MetricsDashboardView
from clients.views.onboarding_start_contact import onboarding_start_contact as onboarding_start
from clients.views.onboarding_step_return import (
    onboarding_address,
    onboarding_declarations,
    onboarding_digital_access,
    onboarding_passport,
    onboarding_personal_extra,
    onboarding_travel,
)
from clients.views.onboarding_token_access import enable_token_link_access
from clients.views.onboarding_views import (
    check_onboarding_session,
    generate_onboarding_link,
    onboarding_ask_question,
    onboarding_auto_save,
    onboarding_document_delete,
    onboarding_document_preview,
    onboarding_document_upload,
    onboarding_personal_data,
    onboarding_purpose,
    onboarding_review,
    onboarding_select_case,
    onboarding_set_password,
    quick_create_client_onboarding,
)
from clients.views.payments import *  # noqa: F403
from clients.views.print_views import *  # noqa: F403
from clients.views.reminders import *  # noqa: F403
from clients.views.schedule_views import fingerprints_schedule_view
from clients.views.staff_views import *  # noqa: F403
from clients.views.tasks import *  # noqa: F403
from clients.views.testcenter import testcenter_view
from clients.views.workday import WorkdayView

enable_token_link_access()

__all__ = [name for name in globals() if not name.startswith('_')]
