"""
Rate limiting middleware для защиты от злоупотреблений.

Использование кеша Django для отслеживания запросов.
"""

import time
from django.core.cache import cache
from django.http import HttpResponse
from django.conf import settings


class RateLimitMiddleware:
    """
    Middleware для ограничения количества запросов.
    
    Лимиты по умолчанию:
    - 100 запросов в минуту для обычных пользователей
    - 300 запросов в минуту для авторизованных пользователей
    - 30 POST запросов в минуту (форм)
    """
    
    def __init__(self, get_response):
        self.get_response = get_response
        
        # Лимиты из settings или defaults
        self.limits = getattr(settings, 'RATE_LIMITS', {
            'anonymous': 100,      # запросов в минуту
            'authenticated': 300,  # запросов в минуту
            'post': 30,           # POST запросов в минуту
        })
        
        # Исключения (эндпоинты без лимитов)
        self.exempt_paths = getattr(settings, 'RATE_LIMIT_EXEMPT_PATHS', [
            '/static/',
            '/media/',
            '/__debug__/',  # Django Debug Toolbar
        ])
    
    def __call__(self, request):
        # Пропускаем статику и исключения
        if self._is_exempt(request.path):
            return self.get_response(request)
        
        # Получаем IP адрес
        ip_address = self._get_client_ip(request)
        
        # Проверяем лимит
        if not self._check_rate_limit(request, ip_address):
            return self._rate_limit_response()
        
        return self.get_response(request)
    
    def _is_exempt(self, path):
        """Проверить что путь в исключениях."""
        return any(path.startswith(exempt) for exempt in self.exempt_paths)
    
    def _get_client_ip(self, request):
        """Получить IP адрес клиента."""
        # Проверяем заголовки прокси
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0].strip()
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip
    
    def _check_rate_limit(self, request, ip_address):
        """
        Проверить лимит запросов.
        
        Returns:
            bool: True если лимит не превышен, False если превышен
        """
        # Определяем лимит
        if request.method == 'POST':
            limit = self.limits['post']
            cache_key = f'rate_limit:post:{ip_address}'
        elif request.user.is_authenticated:
            limit = self.limits['authenticated']
            cache_key = f'rate_limit:auth:{ip_address}'
        else:
            limit = self.limits['anonymous']
            cache_key = f'rate_limit:anon:{ip_address}'
        
        # Получаем текущее количество запросов
        current = cache.get(cache_key, 0)
        
        if current >= limit:
            return False
        
        # Увеличиваем счетчик
        if current == 0:
            # Первый запрос - устанавливаем TTL на 60 секунд
            cache.set(cache_key, 1, 60)
        else:
            # Инкрементим без изменения TTL
            cache.incr(cache_key)
        
        return True
    
    def _rate_limit_response(self):
        """Ответ при превышении лимита."""
        response = HttpResponse(
            '<h1>429 Too Many Requests</h1>'
            '<p>Вы превысили лимит запросов. Пожалуйста, подождите минуту.</p>'
            '<p>You have exceeded the rate limit. Please wait a minute.</p>',
            status=429
        )
        response['Retry-After'] = '60'
        return response


# Декоратор для конкретных view
def rate_limit(limit=30, period=60):
    """
    Декоратор для ограничения конкретных view.
    
    Args:
        limit: Максимум запросов
        period: Период в секундах
    
    Example:
        @rate_limit(limit=10, period=60)
        def upload_document(request):
            ...
    """
    def decorator(view_func):
        def wrapper(request, *args, **kwargs):
            ip = get_client_ip(request)
            cache_key = f'rate_limit:{view_func.__name__}:{ip}'
            
            current = cache.get(cache_key, 0)
            
            if current >= limit:
                return HttpResponse(
                    f'Too many requests. Limit: {limit} per {period}s',
                    status=429
                )
            
            if current == 0:
                cache.set(cache_key, 1, period)
            else:
                cache.incr(cache_key)
            
            return view_func(request, *args, **kwargs)
        
        return wrapper
    return decorator


def get_client_ip(request):
    """Получить IP адрес из request."""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0].strip()
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip
