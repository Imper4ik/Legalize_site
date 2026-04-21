# legalize_site/urls.py

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import path, include
from django.conf.urls.i18n import i18n_patterns
from clients import views
from clients.views.admin_views import update_translations_view
from users.views import ResendVerificationEmailView
from .cron_views import db_backup, process_email_campaigns_cron

from legalize_site.views import healthcheck

urlpatterns = [
    path('healthz/', healthcheck, name='healthcheck'),
    path('admin/update-translations/', update_translations_view, name='update_translations'),
    path('admin/', admin.site.urls),
    path('i18n/', include('django.conf.urls.i18n')),
    path('cron/db-backup/', db_backup, name='db_backup'),
    path('cron/process-email-campaigns/', process_email_campaigns_cron, name='process_email_campaigns_cron'),
]

if getattr(settings, "ENABLE_TRANSLATION_TOOLING", False) and 'rosetta' in settings.INSTALLED_APPS:
    urlpatterns += [
        path('rosetta/', include('rosetta.urls')),
        path('studio/', include('translations.urls', namespace='translations')),
    ]

urlpatterns += i18n_patterns(
    path(
        "accounts/confirm-email/resend/",
        ResendVerificationEmailView.as_view(),
        name="account_resend_verification",
    ),
    path('accounts/', include('allauth.urls')),
    path('staff/', include('clients.urls', namespace='clients')),
    path('submissions/', include('submissions.urls', namespace='submissions')),

    # Эта строка теперь будет главной страницей после входа
    path('', views.dashboard_redirect_view, name='root_dashboard'),
)

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
