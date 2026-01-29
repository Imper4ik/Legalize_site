"""
Backup Trigger View - для вызова бэкапа через внешний cron.

Security: защищено secret token из environment variables.
"""
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.core.management import call_command
from django.conf import settings
import logging

logger = logging.getLogger(__name__)


@csrf_exempt
@require_http_methods(["POST", "GET"])  # GET для тестирования
def trigger_backup(request):
    """
    Endpoint для триггера автоматического бэкапа.
    
    Предназначен для вызова через внешний cron-сервис (например, cron-job.org).
    
    Security:
        - Проверяет secret token из query параметров или POST данных
        - Логирует все попытки доступа
        - Возвращает минимальную информацию при ошибках
    
    Usage:
        POST/GET https://your-app.railway.app/api/backup/trigger/?secret=YOUR_SECRET
    
    Returns:
        JSON с результатом выполнения бэкапа
    """
    # Получить secret из request
    secret = request.GET.get('secret') or request.POST.get('secret')
    
    # Проверить, что secret настроен
    expected_secret = settings.BACKUP_TRIGGER_SECRET
    if not expected_secret:
        logger.error('BACKUP_TRIGGER_SECRET not configured in settings')
        return JsonResponse({
            'status': 'error',
            'message': 'Backup trigger not configured'
        }, status=500)
    
    # Проверить secret
    if not secret or secret != expected_secret:
        # Логировать неудачную попытку
        ip = request.META.get('HTTP_X_FORWARDED_FOR', request.META.get('REMOTE_ADDR', 'unknown'))
        logger.warning(f'Unauthorized backup trigger attempt from IP: {ip}')
        
        return JsonResponse({
            'status': 'error',
            'message': 'Unauthorized'
        }, status=403)
    
    # Выполнить бэкап
    try:
        logger.info('Starting automated database backup...')
        
        # Вызвать команду dbbackup с опцией --clean для удаления старых бэкапов
        call_command('dbbackup', '--clean', verbosity=1)
        
        logger.info('✓ Automated backup completed successfully')
        
        return JsonResponse({
            'status': 'success',
            'message': 'Database backup completed successfully'
        })
        
    except Exception as e:
        logger.error(f'Backup failed: {str(e)}', exc_info=True)
        
        return JsonResponse({
            'status': 'error',
            'message': f'Backup failed: {str(e)}'
        }, status=500)


@csrf_exempt
@require_http_methods(["GET"])
def backup_status(request):
    """
    Проверить статус последнего бэкапа.
    
    Returns информацию о последнем файле бэкапа.
    """
    # Проверить secret
    secret = request.GET.get('secret')
    expected_secret = settings.BACKUP_TRIGGER_SECRET
    
    if not secret or not expected_secret or secret != expected_secret:
        return JsonResponse({'status': 'error', 'message': 'Unauthorized'}, status=403)
    
    try:
        from dbbackup.storage import get_storage
        from django.utils import timezone
        
        storage = get_storage()
        files = list(storage.list_directory(''))
        
        if not files:
            return JsonResponse({
                'status': 'warning',
                'message': 'No backups found',
                'backup_count': 0
            })
        
        # Получить информацию о последнем бэкапе
        latest = max(files, key=lambda f: storage.get_modified_time(f))
        modified = storage.get_modified_time(latest)
        age = timezone.now() - modified
        
        return JsonResponse({
            'status': 'success',
            'latest_backup': latest,
            'created_at': modified.isoformat(),
            'age_hours': int(age.total_seconds() / 3600),
            'backup_count': len(files)
        })
        
    except Exception as e:
        logger.error(f'Failed to get backup status: {str(e)}')
        return JsonResponse({
            'status': 'error',
            'message': str(e)
        }, status=500)
