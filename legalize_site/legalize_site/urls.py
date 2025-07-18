# legalize_site/legalize_site/urls.py

from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from clients import views

urlpatterns = [
    path('admin/', admin.site.urls),

    # Все адреса для аутентификации (вход, выход, регистрация)
    path('accounts/', include('allauth.urls')),

    # Все адреса для клиентского портала (личный кабинет)
    path('portal/', include('portal.urls', namespace='portal')),

    # Все адреса для сотрудников (список клиентов, калькулятор и т.д.)
    path('staff/', include('clients.urls', namespace='clients')),

    # Главная страница сайта, которая перенаправляет куда нужно
    path('', views.dashboard_redirect, name='root_dashboard'),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)