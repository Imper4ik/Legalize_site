# legalize_site/urls.py (ФИНАЛЬНАЯ ИСПРАВЛЕННАЯ ВЕРСИЯ)

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import path, include
from django.conf.urls.i18n import i18n_patterns
from clients import views

# URL-адреса, которые не будут иметь языкового префикса
urlpatterns = [
    path('admin/', admin.site.urls),
    path('i18n/', include('django.conf.urls.i18n')),
]

# URL-адреса, которые будут многоязычными
urlpatterns += i18n_patterns(
    # Этот путь отвечает за регистрацию, вход, сброс пароля и т.д.
    path('accounts/', include('allauth.urls')),

    # Все URL-адреса из приложения для персонала будут начинаться с /staff/
    path('staff/', include('clients.urls', namespace='clients')),

    # Все URL-адреса из клиентского портала будут доступны с корневого уровня.
    # Это включает и вашу форму-анкету.
    path('', include('portal.urls', namespace='portal')),

    # ПРИМЕЧАНИЕ: Если у вас есть главный дашборд, его URL должен быть
    # определен внутри portal/urls.py как path('', ...), а не здесь.
    # Строка с `dashboard_redirect` здесь создавала конфликт.
)

# Настройка для медиафайлов в режиме отладки
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)