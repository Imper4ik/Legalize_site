# legalize_site/urls.py

from django.conf import settings
from django.conf.urls.i18n import i18n_patterns
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

from clients import views
from clients.views.admin_views import update_translations_view
from legalize_site.views import healthcheck, readiness
from users.security_views import SignupDisabledView
from users.views import ResendVerificationEmailView

from .cron_views import (
    db_backup,
    process_document_jobs_cron,
    process_email_campaigns_cron,
    retention_maintenance_cron,
    update_reminders_cron,
)

urlpatterns = [
    path('healthz/', healthcheck, name='healthcheck'),
    path('readyz/', readiness, name='readiness'),
    path('admin/update-translations/', update_translations_view, name='update_translations'),
    path('admin/', admin.site.urls),
    path('i18n/', include('django.conf.urls.i18n')),
    path('cron/db-backup/', db_backup, name='db_backup'),
    path('cron/process-email-campaigns/', process_email_campaigns_cron, name='process_email_campaigns_cron'),
    path('cron/process-document-jobs/', process_document_jobs_cron, name='process_document_jobs_cron'),
    path('cron/update-reminders/', update_reminders_cron, name='update_reminders_cron'),
    path('cron/run-maintenance/', retention_maintenance_cron, name='run_maintenance_cron'),
    path('cron/retention-maintenance/', retention_maintenance_cron, name='retention_maintenance_cron'),
]

if getattr(settings, "ENABLE_TRANSLATION_TOOLING", False):
    if 'rosetta' in settings.INSTALLED_APPS:
        urlpatterns.append(path('rosetta/', include('rosetta.urls')))
    if 'translations' in settings.INSTALLED_APPS:
        urlpatterns.append(path('studio/', include('translations.urls', namespace='translations')))

urlpatterns += i18n_patterns(
    path("accounts/signup/", SignupDisabledView.as_view(), name="account_signup"),
    path("accounts/social/signup/", SignupDisabledView.as_view(), name="socialaccount_signup"),
    path(
        "accounts/confirm-email/resend/",
        ResendVerificationEmailView.as_view(),
        name="account_resend_verification",
    ),
    path('accounts/', include('allauth.urls')),
    path('privacy/', views.privacy_policy_view, name='privacy_policy'),
    path('staff/', include('clients.urls', namespace='clients')),
    path('submissions/', include('submissions.urls', namespace='submissions')),

    # Эта строка теперь будет главной страницей после входа
    path('', views.dashboard_redirect_view, name='root_dashboard'),
)

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
